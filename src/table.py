import re
from itertools import product
import warnings
from datetime import datetime



class table:

	def __table_to_2d(self, t, config):
		"""
		transform tables from nested lists to JSON

		Args:
			t: html table, beautiful soup object
			config: configuration dictionary

		Returns:
			table: table in JSON format

		"""
		# https://stackoverflow.com/questions/48393253/how-to-parse-table-with-rowspan-and-colspan
		rows = t.find_all('tr')
		# fill colspan and rowspan
		for row in rows:
			for col in row.findAll(['th','td']):
				if 'colspan' not in col.attrs:
					col.attrs['colspan'] = 1
				if 'rowspan' not in col.attrs:
					col.attrs['rowspan'] = 1

		# first scan, see how many columns we need
		n_cols = sum([int(i.attrs['colspan']) for i in t.find('tr').findAll(['th','td'])])

		# build an empty matrix for all possible cells
		table = [[''] * n_cols for row in rows]

		# fill matrix from row data
		rowspans = {}  # track pending rowspans, column number mapping to count
		for row_idx, row in enumerate(rows):
			span_offset = 0  # how many columns are skipped due to row and colspans
			for col_idx, cell in enumerate(row.findAll(['td', 'th'])):
				# adjust for preceding row and colspans
				col_idx += span_offset
				while rowspans.get(col_idx, 0):
					span_offset += 1
					col_idx += 1

				# fill table data
				rowspan = rowspans[col_idx] = int(cell.attrs['rowspan'])
				colspan = int(cell.attrs['colspan'])
				# next column is offset by the colspan
				span_offset += colspan - 1
				value = ''.join(str(x) for x in cell.contents)
				# value = cell.get_text()
				# clean the cell
				value = value.strip().replace('\u2009',' ')
				value = re.sub("<\/?span[^>\n]*>?|<hr\/>?", "", value)
				if value.startswith('(') and value.endswith(')'):
					value = value[1:-1]
				if re.match(self.pval_regex,value):
					value = re.sub(r'(\s{0,1})[*××xX](\s{0,1})10(_{0,1})','e',value).replace('−', '-')
				if re.match(self.pval_scientific_regex,value):
					value = re.sub(r'(\s{0,1})[–−-](\s{0,1})','-',value)
					value = re.sub(r'(\s{0,1})[eE]','e',value)
				for drow, dcol in product(range(rowspan), range(colspan)):
					try:
						table[row_idx + drow][col_idx + dcol] = value
						rowspans[col_idx + dcol] = rowspan
					except IndexError:
						# rowspan or colspan outside the confines of the table
						pass
			# update rowspan bookkeeping
			rowspans = {c: s - 1 for c, s in rowspans.items() if s > 1}
		return table

	def __check_superrow(self, row):
		"""
		check if the current row is a superrow

		Args:
			row: python list

		Return:
			True/False

		"""
		if len(set([i for i in row if (str(i)!='')&(str(i)!='\n')&(str(i)!='None')]))==1:
			return True
		else:
			return False

	def __find_format(self, header):
		"""
		determine if there exists a splittable pattern in the header cell

		Args:
			header: single header str

		Returns:
			pattern: regex object

		Raises:
			KeyError: Raises an exception.
		"""

		if header=='':
			return None
		#     parts = nltk.tokenize.word_tokenize(header)
		a = re.split(r'[:|/,;]', header)
		b = re.findall(r'[:|/,;]', header)
		parts = []
		for i in range(len(b)):
			parts+=[a[i],b[i]]
		parts.append(a[-1])

		# identify special character
		special_char_idx = []
		for idx,part in enumerate(parts):
			if part in ':|\/,;':
				special_char_idx.append(idx)

		# generate regex pattern
		if special_char_idx:
			pattern = r''
			for idx in range(len(parts)):
				if idx in special_char_idx:
					char = parts[idx]
					pattern+='({})'.format(char)
				else:
					pattern+='(\w+)'
			pattern = re.compile(pattern)
			return pattern
		else:
			return None

	def __test_format(self, pattern, s):
		"""
		check if the element conforms to the regex pattern

		Args:
			header: single header str
			s: element in string format

		Returns:
			result: bool

		Raises:
			KeyError: Raises an exception.
		"""

		if re.search(pattern,s):
			return True
		return False

	def __split_format(self, pattern, s):
		"""
		split s according to regex pattern

		Args:
			pattern: regex object
			s: element in string format

		Returns:
			list of substrings

		Raises:
			KeyError: Raises an exception.
		"""
		return [i for i in re.split(r'[:|/,;]', s) if i not in ':|\/,;']

	def __get_headers(self, t, config):
		"""
		identify headers from a table

		Args:
			t: BeautifulSoup object of table

		Returns:
			idx_list: a list of header index

		Raises:
			KeyError: Raises an exception.
		"""
		idx_list = []
		for idx,row in enumerate(t.find_all(config['table_row']['name'],config['table_row']['attrs'])):
			if row.find_all(config['table_header_element']['name'],config['table_header_element']['attrs']):
				idx_list.append(idx)
			elif 'class' in row.attrs:
				if 'thead' in row.attrs['class']:
					idx_list.append(idx)

		# if no table headers found
		if idx_list==[]:
			idx_list=[0]
		return idx_list

	def __get_superrows(self, t):
		"""
		determine supperrows in a table

		Args:
			t: BeautifulSoup object of table

		Returns:
			idx_list: a list of superrow index

		"""
		idx_list = []
		for idx,row in enumerate(t):
			if idx not in self.__get_headers(t):
				if self.__check_superrow(row):
					idx_list.append(idx)
		return idx_list

	def __is_number(self, s):
		"""
		check if input string is a number

		Args:
			s: input string

		Returns:
			True/False

		"""
		try:
			float(s.replace(',',''))
			return True
		except ValueError:
			return False

	def __is_mix(self, s):
		"""
		check if input string is a mix of number and text

		Args:
			s: input string

		Returns:
			True/False

		"""
		if any(char.isdigit() for char in s):
			if any(char for char in s if char.isdigit()==False):
				return True
		return False

	def __is_text(self, s):
		"""
		check if input string is all text

		Args:
			s: input string

		Returns:
			True/False

		"""
		if any(char.isdigit() for char in s):
			return False
		return True

	def __table2json(self, table_2d, header_idx, subheader_idx, superrow_idx, table_num, title, footer, caption):
		"""
		transform tables from nested lists to JSON

		Args:
			table_2d: nested list tables
			header_idx: list of header indices
			subheader_idx: list of subheader indices
			superrow_idx: list of superrow indices
			table_num: table number
			caption: table caption
			footer: table footer

		Returns:
			tables: tables in JSON format

		"""
		tables = []
		sections = []
		cur_table = {}
		cur_section = {}

		pre_header = []
		pre_superrow = None
		cur_header = ''
		cur_superrow = ''
		for row_idx,row in enumerate(table_2d):
			if not any([i for i in row if i not in ['','None']]):
				continue
			if row_idx in header_idx:
				cur_header = [table_2d[i] for i in [i for i in subheader_idx if row_idx in i][0]]
			elif row_idx in superrow_idx:
				cur_superrow = [i for i in row if i not in ['','None']][0]
			else:
				if cur_header!=pre_header:
					sections = []
					pre_superrow = None
					cur_table = {'identifier':str(table_num+1),
					             'title':title,
					             'caption': caption,
					             'columns':cur_header,
					             'section':sections,
					             'footer':footer}
					tables.append(cur_table)
				elif cur_header==pre_header:
					cur_table['section'] = sections
				if cur_superrow!=pre_superrow:
					cur_section = {'section_name':cur_superrow,
					               'results': [row]}
					sections.append(cur_section)
				elif cur_superrow==pre_superrow:
					cur_section['results'].append(row)

				pre_header = cur_header
				pre_superrow = cur_superrow

		if len(tables)>1:
			for table_idx,table in enumerate(tables):
				table['identifier'] += '.{}'.format(table_idx+1)
		return tables

	def __table2json4prep(self, table_num, title, footer, caption):
		"""
		transform tables from nested lists to JSON

		Args:
		    table_num: table number
		    caption: table caption
		    footer: table footer

		Returns:
		    tables: tables in JSON format

		"""
		tables = []
		sections = []
		cur_table = {}

		pre_header = []
		cur_header = ''

		if cur_header!=pre_header:
		    sections = []
		    cur_table = {'identifier':str(table_num+1),
				 'title':title,
				 'caption': caption,
				 'columns':cur_header,
				 'section':sections,
				 'footer':footer}
		    tables.append(cur_table)
		elif cur_header==pre_header:
		    cur_table['section'] = sections

		pre_header = cur_header

		if len(tables)>1:
		    for table_idx,table in enumerate(tables):
			table['identifier'] += '.{}'.format(table_idx+1)
		return tables
	
	def __reformat_table_json(self, table_json):
		bioc_format = {
			"source": "Auto-CORPus table processing",
			"date": f'{datetime.today().strftime("%Y%m%d")}',
			"key": "auto-corpus-table.key",
			"infons": {},
			"documents":[]
		}

		for table in table_json['tables']:
			offset = 0
			tableDict = {
				"file": self.file_name,
				"id": F"T{self.tableIdentifier if self.tableIdentifier else table['identifier']}",
				"infons": {},
				"passages":[
					{
						"offset": 0,
						"infons":{
							"section_type": [
								{"type": "table_title",
								"IAO_name": "document title",
								 "IAO_id": "IAO:0000305"
								 }
							]
						},
						"text": table['title'],
						"sentences": [],
						"annotations": [],
						"relations": []
					}
				],
				"annotations": [],
				"relations": []
			}
			offset += len(table['title'])
			if "caption" in table.keys():
				tableDict['passages'].append(
					{
						"offset": offset,
						"infons":{
							"section_type":[
								{
									"type": "table_caption",
									"IAO_name": "caption",
									"IAO_id": "IAO:0000304"
								}
							]
						},
						"text": ". ".join(table["caption"]),
						"sentences": [],
						"annotations": [],
						"relations": []
					}
				)
				offset += len("".join(table["caption"]))

			if "section" in table.keys():
				rowID = 0
				colID = 0
				rsection = []
				this_offset = offset
				for sect in table["section"]:

					resultsDict = 						{
						"section_title_1": sect['section_name'],
						"results_rows":[]
					}
					for resultrow in sect["results"]:
						colID=0
						rrow = []
						for result in resultrow:
							resultDict = {
								"id": F"T{table['identifier']}.{rowID}.{colID}",
								"text": result
							}
							colID+=1
							offset+= len(str(result))
							rrow.append(resultDict)
						resultsDict["results_rows"].append(rrow)
						rowID+=1
					rsection.append(resultsDict)
				tableDict['passages'].append(
					{
						"offset": this_offset,
						"infons": {
							"section_type": [
								{
									"type": "table",
									"IAO_name": "table",
									"IAO_id": "IAO:0000306"
								}
							]
						},
						"columns": table.get("columns", []),
						"results_section": rsection,
						"sentences": [],
						"annotations": [],
						"relations": []
					}
				)

			if "footer" in table.keys():
				tableDict['passages'].append(
					{
						"offset": offset,
						"infons":{
							"section_type":[
								{
									"type": "table_footer",
									"IAO_name": "caption",
									"IAO_id": "IAO:0000304"
								}
							]
						},
						"text": ". ".join(table["footer"]),
						"sentences": [],
						"annotations": [],
						"relations": []
					}
				)
				offset += len("".join(table["footer"]))
			bioc_format["documents"].append(tableDict)
		return bioc_format
        
	def __reformat_table_json4prep(self, table_json):
		bioc_format = {
		    "source": "Auto-CORPus table processing",
		    "date": f'{datetime.today().strftime("%Y%m%d")}',
		    "key": "auto-corpus-table.key",
		    "infons": {},
		    "documents":[]
		}

		for table in table_json['tables']:
		    offset = 0
		    tableDict = {
			"file": self.file_name,
			"id": F"T{self.tableIdentifier if self.tableIdentifier else table['identifier']}",
			"infons": {},
			"passages":[
			    {
				"offset": 0,
				"infons":{
				    "section_type": [
					{"type": "table_title",
					"IAO_name": "document title",
					 "IAO_id": "IAO:0000305"
					 }
				    ]
				},
				"text": table['title'],
				"sentences": [],
				"annotations": [],
				"relations": []
			    }
			],
			"annotations": [],
			"relations": []
		    }
		    offset += len(table['title'])
		    if "caption" in table.keys():
			tableDict['passages'].append(
			    {
				"offset": offset,
				"infons":{
				    "section_type":[
					{
					    "type": "table_caption",
					    "IAO_name": "caption",
					    "IAO_id": "IAO:0000304"
					}
				    ]
				},
				"text": table["caption"],
				"sentences": [],
				"annotations": [],
				"relations": []
			    }
			)
			offset += len("".join(table["caption"]))

		    if "section" in table.keys():
			rowID = 0
			colID = 0
			rsection = []
			this_offset = offset
			for sect in table["section"]:

			    resultsDict =                         {
				"section_title_1": sect['section_name'],
				"results_rows":[]
			    }
			    for resultrow in sect["results"]:
				colID=0
				rrow = []
				for result in resultrow:
				    resultDict = {
					"id": F"T{table['identifier']}.{rowID}.{colID}",
					"text": result
				    }
				    colID+=1
				    offset+= len(str(result))
				    rrow.append(resultDict)
				resultsDict["results_rows"].append(rrow)
				rowID+=1
			    rsection.append(resultsDict)
			tableDict['passages'].append(
			    {
				"offset": this_offset,
				"infons": {
				    "section_type": [
					{
					    "type": "table",
					    "IAO_name": "table",
					    "IAO_id": "IAO:0000306"
					}
				    ]
				},
				"columns": table.get("columns", []),
				"results_section": rsection,
				"sentences": [],
				"annotations": [],
				"relations": []
			    }
			)

		    if "footer" in table.keys():
			tableDict['passages'].append(
			    {
				"offset": offset,
				"infons":{
				    "section_type":[
					{
					    "type": "table_footer",
					    "IAO_name": "caption",
					    "IAO_id": "IAO:0000304"
					}
				    ]
				},
				"text": ". ".join(table["footer"]),
				"sentences": [],
				"annotations": [],
				"relations": []
			    }
			)
			offset += len("".join(table["footer"]))
		    bioc_format["documents"].append(tableDict)
		return bioc_format
	
	def __main(self, soup, config):
		soup_tables = soup.find_all(config['table']['name'],config['table']['attrs'],recursive=True)

		# remove empty table and other table classes
		pop_list = []
		for i,table in enumerate(soup_tables):
			if 'class' in table.attrs:
				if 'table-group' in table.attrs['class']:
					pop_list.append(i)
			if table.find_all('tbody')==[]:
				pop_list.append(i)
				warnings.warn("Table {} has no data rows".format(i))
		soup_tables1 = [soup_tables[i] for i in range(len(soup_tables)) if i in pop_list]
		soup_tables = [soup_tables[i] for i in range(len(soup_tables)) if i not in pop_list]

		tables = []
		for table_num1, table1 in enumerate(soup_tables1):
		    # caption and footer
		    try:
			caption1 = table1.find_next(config['table_title']['name'],config['table_title']['attrs']).get_text()
		    except:
			caption1 = ''
			# warnings.warn("Unable to find table caption")
		    try:
			actual_caption1 = table1.next_sibling.find(config['table_caption']['name'], config['table_caption']['attrs']).get_text()
		    except:
			actual_caption1 = ''
		    cur_table1 = self.__table2json4prep(table_num1, caption1, "", actual_caption1)
		    tables+=cur_table1
		
		# One table
		if soup_tables:
			tables = []
		for table_num, table in enumerate(soup_tables):
			# caption and footer
			try:
				caption = table.find_previous(config['table_title']['name'],config['table_title']['attrs']).get_text()
			except:
				caption = ''
				# warnings.warn("Unable to find table caption")
			try:
				footer = [i.get_text() for i in table.parent.find_next_siblings(config['table_footer']['name'],config['table_footer']['attrs'])]
			except:
				footer = ''
				# warnings.warn("Unable to find table footer")
			try:
				actual_caption = [i.get_text() for i in table.find_previous(config['table_caption']['name'], config['table_caption']['attrs'])]
			except:
				actual_caption = ''
				# warnings.warn("Unable to find actual table caption caption")


			# remove empty table header
			if table.find('td','thead-hr'):
				table.find('td','thead-hr').parent.extract()

			header_idx = self.__get_headers(table,config)

			# span table to single-cells
			table_2d = self.__table_to_2d(table,config)

			# find superrows
			superrow_idx = []
			if table_2d!=None:
				for row_idx,row in enumerate(table_2d):
					if row_idx not in header_idx:
						if self.__check_superrow(row):
							superrow_idx.append(row_idx)

			# identify section names in index column
			if superrow_idx==[]:
				first_col = [row[0] for row in table_2d]
				first_col_vals = [i for i in first_col if first_col.index(i) not in header_idx]
				unique_vals = set([i for i in first_col_vals if i not in ['','None']])
				if len(unique_vals)<=len(first_col_vals)/2:
					section_names = list(unique_vals)
					for i in section_names:
						superrow_idx.append(first_col.index(i))
					n_cols = len(table_2d[0])
					for idx,val in zip(superrow_idx, section_names):
						table_2d = table_2d[:idx]+[[val]*n_cols]+table_2d[idx:]
					#update superrow_idx after superrow insertion
					superrow_idx = []
					first_col = [row[0] for row in table_2d]
					for i in section_names:
						superrow_idx.append(first_col.index(i))
					for row in table_2d:
						row.pop(0)

			# Identify subheaders
			value_idx = [i for i in range(len(table_2d)) if i not in header_idx+superrow_idx]
			col_type = []
			for col_idx in range(len(table_2d[0])):
				cur_col = [i[col_idx] for i in table_2d]
				num_cnt = 0
				txt_cnt = 0
				mix_cnt = 0
				for cell in cur_col:
					cell = str(cell).lower()
					if cell in ['none', '', '-',]:
						continue
					elif self.__is_number(cell):
						num_cnt+=1
					elif self.__is_mix(cell):
						mix_cnt+=1
					elif self.__is_text(cell):
						txt_cnt+=1
				if max(num_cnt,txt_cnt,mix_cnt)==num_cnt:
					col_type.append('num')
				elif max(num_cnt,txt_cnt,mix_cnt)==txt_cnt:
					col_type.append('txt')
				else:
					col_type.append('mix')
			subheader_idx = []
			for row_idx in value_idx:
				cur_row = table_2d[row_idx]
				unmatch_cnt = 0
				for col_idx in range(len(cur_row)):
					cell = str(cur_row[col_idx]).lower()
					if self.__is_text(cell) and col_type[col_idx]!='txt' and cell not in ['none', '', '-',]:
						unmatch_cnt+=1
				if unmatch_cnt>=len(cur_row)/2:
					subheader_idx.append(row_idx)
			header_idx+=subheader_idx

			subheader_idx = []
			tmp = [header_idx[0]]
			for i,j in zip(header_idx,header_idx[1:]):
				if j==i+1:
					tmp.append(j)
				else:
					subheader_idx.append(tmp)
					tmp=[j]
			subheader_idx.append(tmp)

			# convert to float
			for row in table_2d:
				for cell in range(len(row)):
					try:
						row[cell] = float(row[cell].replace('−','-').replace('–','-').replace(',',''))
					except:
						row[cell] = row[cell]

			cur_table = self.__table2json(table_2d, header_idx, subheader_idx, superrow_idx, table_num, caption, footer, actual_caption)
			# merge headers
			sep = '<!>'
			for table in cur_table:
				headers = table['columns']
				new_header = []
				for col_idx in range(len(headers[0])):
					new_element = ''
					for r_idx in range(len(headers)):
						new_element += str(headers[r_idx][col_idx])+sep
					new_element = new_element.rstrip(sep)
					new_header.append(new_element)
				table['columns'] = new_header

			tables+=cur_table

		table_json = {'tables':tables}
		if soup_tables:
		    table_json = self.__reformat_table_json(table_json)
		else:
		    table_json = self.__reformat_table_json4prep(table_json)
		return table_json



	def __init__(self, soup, config, file_name):
		self.file_name = file_name
		self.tableIdentifier=None
		if re.search("_table_\d+\.html", file_name):
			self.tableIdentifier = file_name.split("/")[-1].split("_")[-1].split(".")[0]
		self.pval_regex = r'((\d+\.\d+)|(\d+))(\s?)[*××xX](\s{0,1})10[_]{0,1}([–−-])(\d+)'
		self.pval_scientific_regex = r'((\d+.\d+)|(\d+))(\s{0,1})[eE](\s{0,1})([–−-])(\s{0,1})(\d+)'
		self.tables = self.__main(soup, config)
		pass

	def to_dict(self):
		return self.tables

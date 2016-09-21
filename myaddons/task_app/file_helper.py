# -*- coding: utf-8 -*-
import base64
import csv
import itertools
import logging
import operator

import xlrd

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from openerp.tools.translate import _
from openerp.osv import osv

_logger = logging.getLogger(__name__)


class file_helper:
    def debug(self):
        print "-----------------"

    def _read_csv(self, record, options):
        """ Returns a CSV-parsed iterator of all empty lines in the file

        :throws csv.Error: if an error is detected during CSV parsing
        :throws UnicodeDecodeError: if ``options.encoding`` is incorrect
        """
        csv_iterator = csv.reader(
            StringIO(record.file),
            quotechar=str(options['quoting']),
            delimiter=str(options['separator']))

        def nonempty(row):
            return any(x for x in row if x.strip())

        csv_nonempty = itertools.ifilter(nonempty, csv_iterator)
        # TODO: guess encoding with chardet? Or https://github.com/aadsm/jschardet
        encoding = options.get('encoding', 'utf-8')

        return itertools.imap(
            lambda row: [item.decode(encoding) for item in row],
            csv_nonempty)

    def _convert_import_data(self, record, fields, options, context=None):
        """ Extracts the input browse_record and fields list (with
        ``False``-y placeholders for fields to *not* import) into a
        format Model.import_data can use: a fields list without holes
        and the precisely matching data matrix

        :param browse_record record:
        :param list(str|bool): fields
        :returns: (data, fields)
        :rtype: (list(list(str)), list(str))
        :raises ValueError: in case the import data could not be converted
        """
        # Get indices for non-empty fields
        indices = [index for index, field in enumerate(fields) if field]
        if not indices:
            raise ValueError(_("You must configure at least one field to import"))
        # If only one index, itemgetter will return an atom rather
        # than a 1-tuple
        if len(indices) == 1:
            mapper = lambda row: [row[indices[0]]]
        else:
            mapper = operator.itemgetter(*indices)
        # Get only list of actually imported fields
        import_fields = filter(None, fields)

        rows_to_import = self._read_csv(record, options)
        if options.get('headers'):
            rows_to_import = itertools.islice(rows_to_import, 1, None)
        data = [
            row for row in itertools.imap(mapper, rows_to_import)
            # don't try inserting completely empty rows (e.g. from
            # filtering out o2m fields)
            if any(row)
            ]

        return data, import_fields

    def _check_import_file_columes(self, require_fields, colnames):
        for f in require_fields:
            if f not in colnames:
                raise osv.except_osv(_('Error!'), _('导入文件缺少数据列: ' + f))

    def retrieve_items(self, binary_field, record, require_fields):
        # this = self.browse(cr, uid, ids[0])
        # (record,) = self.browse(cr, uid, [id], context=context)

        record.file = base64.decodestring(binary_field)
        items = []

        # read csv file.
        import_fields = []
        try:
            options = {'headers': True, 'quoting': '"', 'separator': ',', 'encoding': 'gb2312'}

            data, import_fields = self._convert_import_data(record, require_fields, options, context=context)
        except:
            pass
        if len(import_fields) != 0:
            self._check_import_file_columes(require_fields, import_fields)

            _logger.info('importing %d rows...', len(data))

            _logger.info('header: %s', import_fields)
            for d in data:
                items.append(dict(zip(import_fields, d)))
                # _logger.info('import item: %s', d)

            return items

        # read xls file.
        book = None
        try:
            record.file = base64.decodestring(binary_field)
            book = xlrd.open_workbook(file_contents=record.file)

        except:
            pass

        if book is not None:

            _logger.info('book sheets: %s', len(book.sheets()))

            table = book.sheet_by_index(0)
            nrows = table.nrows  # 行数

            if nrows < 2:
                raise osv.except_osv(_('Error!'), _('导入文件没有采购数据。'))

            items = []
            colnames = [c.encode('utf8') for c in table.row_values(0)]  # 某一行数据

            self._check_import_file_columes(require_fields, colnames)

            for rownum in range(1, nrows):
                row = table.row_values(rownum)
                if row:
                    app = {}
                for i in range(len(colnames)):
                    if colnames[i] == '日期':
                        app[colnames[i]] = xlrd.xldate.xldate_as_datetime(row[i], 0).strftime('%Y-%m-%d')
                    else:
                        app[colnames[i]] = row[i]

                # for i in range(len(colnames)):
                #     if colnames[i] == '煤品种' and this.combine_names:
                #         app[colnames[i]] = app['库房'] + '.' + row[i]

                items.append(app)
            return items

        raise osv.except_osv(_('Error!'), _('导入文件格式不正确，数据导入失败。'))

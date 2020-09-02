import io
import re
from collections import defaultdict
from datetime import datetime
from functools import cmp_to_key

import pytz
from pdfminer.converter import PDFConverter
from pdfminer.layout import LAParams, LTPage, LTCurve, LTFigure, LTImage, LTTextLine, LTTextBox, LTChar, LTText, LTTextGroup
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage

TZ = pytz.timezone('Asia/Jakarta')

class Collector(PDFConverter):

    def __init__(self, rsrcmgr, outfp, codec='utf-8', pageno=1, laparams=None):
        PDFConverter.__init__(self, rsrcmgr, outfp, codec=codec, pageno=pageno,
                              laparams=laparams)

        self.layoutmode = 'normal'
        self._yoffset = 50

        self._font = None
        self._fontstack = []

        self._posstack = []
        self._texts = []

    def place_text(self, color, text, x, y, size):
        color = self.text_colors.get(color)
        if color is not None:
            self._texts.append(((x, (self._yoffset - y)), text))

    def begin_div(self, color, borderwidth, x, y, w, h, writing_mode=False):
        self._fontstack.append(self._font)
        self._font = None
        self._posstack.append((x, (self._yoffset - y), w, h))

    def end_div(self, color):
        self._font = self._fontstack.pop()
        self._posstack.pop()

    def put_text(self, text, fontname, fontsize):
        font = (fontname, fontsize)
        if font != self._font:
            self._font = font
            self._texts.append((self._posstack[-1], ''))

        t = self._texts.pop()
        self._texts.append((t[0], t[1] + text))

    def put_newline(self):
        t = self._texts.pop()
        self._texts.append((t[0], t[1] + '<br>'))

    def receive_layout(self, ltpage):
        def show_group(item):
            if isinstance(item, LTTextGroup):
                for child in item:
                    show_group(child)

        def render(item):
            if isinstance(item, LTPage):
                self._yoffset += item.y1
                for child in item:
                    render(child)
                if item.groups is not None:
                    for group in item.groups:
                        show_group(group)
            elif isinstance(item, LTCurve):
                pass
            elif isinstance(item, LTFigure):
                self.begin_div('figure', 1, item.x0, item.y1, item.width,
                               item.height)
                for child in item:
                    render(child)
                self.end_div('figure')
            elif isinstance(item, LTImage):
                pass
            else:
                if self.layoutmode == 'exact':
                    if isinstance(item, LTTextLine):
                        for child in item:
                            render(child)
                    elif isinstance(item, LTTextBox):
                        self.place_text('textbox', str(item.index+1), item.x0,
                                        item.y1, 20)
                        for child in item:
                            render(child)
                    elif isinstance(item, LTChar):
                        self.place_text('char', item.get_text(), item.x0,
                                        item.y1, item.size)
                else:
                    if isinstance(item, LTTextLine):
                        for child in item:
                            render(child)
                        if self.layoutmode != 'loose':
                            self.put_newline()
                    elif isinstance(item, LTTextBox):
                        self.begin_div('textbox', 1, item.x0, item.y1,
                                       item.width, item.height,
                                       item.get_writing_mode())
                        for child in item:
                            render(child)
                        self.end_div('textbox')
                    elif isinstance(item, LTChar):
                        self.put_text(item.get_text(), item.fontname,
                                      item.size)
                    elif isinstance(item, LTText):
                        pass

        render(ltpage)

    def close(self):
        pass


def parse_number(t):
    return int(re.sub('[^0-9-]', '', t))

def parse_currency_exchange(t):
    m = re.search(r'Transaksi dengan ([A-Z]{3}) \(([0-9.]) ([A-Z]{3}) = ([0-9.]+) ([A-Z]{3})\)', t)
    if not m:
        return 'IDR', 'IDR', 1

    curr_txn = m.group(1)
    curr_acc = m.group(5)
    rate = parse_number(m.group(4))
    return curr_txn, curr_acc, rate

def parse_date(t):
    months = dict(
        Jan=1,
        Feb=2,
        Mar=3,
        Apr=4,
        Mei=5,
        Jun=6,
        Jul=7,
        Agt=8,
        Sep=9,
        Okt=10,
        Nov=11,
        Des=12,
    )

    p = t.split()
    d = int(p[0])
    m = months[p[1]]
    y = int(p[2])
    H, M = list(map(int, p[3].split(':')))
    return datetime(y, m, d, H, M, tzinfo=TZ)

class Data(object):
    def __init__(self, details, transactions):
        self.details = details
        self.transactions = transactions

class Parser(object):
    _table_headers = ['TANGGAL & JAM', 'RINCIAN', 'CATATAN', 'JUMLAH']
    _footer_markers = ['PT Bank BTPN', 'www.jenius.com', '1500 365', 'Jenius Help', 'Disclaimer']
    _detail_fields = {
        'Pemilik Rekening': 'name',
        'Nomor rekening': 'account_number',
        '$Cashtag': 'cashtag',
        'Mata uang': 'currency',
        'Menampilkan transaksi dari': 'account',
        'Nomor Kartu': 'card_number',
    }


    def parse(self, f):
        details = None
        transactions = []

        pages = PDFPage.get_pages(f, caching=False)
        for i, page in enumerate(pages):
            d, t = self._process_page(page, find_details=i==0)
            details = self._merge_details(details, d)
            transactions = self._merge_transactions(transactions, t)

        return Data(details, transactions)

    def _process_page(self, page, find_details=True):
        texts = sorted(self._get_texts(page), key=cmp_to_key(self._cmp_position))
        ymin, ymax = self._get_table_boundaries(texts)
        if ymin == 0:
            return None, []

        content = self._find_content(texts, ymin, ymax)
        cols = self._find_columns(texts, content)
        rows = self._find_rows(texts, cols)
        transactions = self._read_transactions(texts, rows)

        details = None
        if find_details:
            details = self._find_details(texts, ymin)

        return details, transactions

    def _stripws(self, t):
        return re.sub(r'\s+', ' ', t).strip()

    def _stripbr(self, t):
        return re.sub('<br>', ' ', t)


    def _find_details(self, texts, ymin):
        headers = []
        for idx, t in enumerate(texts):
            x, y, w, h = t[0]
            if y >= ymin:
                continue

            tt = t[1]
            headers.append((idx, (x, y), self._stripws(self._stripbr(tt))))

        def find_value(pos, idx):
            closest = None
            for i, p, f in headers:
                if i == idx:
                    continue

                dist = (pos[0] - p[0]) ** 2 + (pos[1] - p[1]) ** 2

                if closest is None or dist < closest[0]:
                    closest = (dist, i, p, f)

            return (closest[1], closest[2], closest[3])

        data = {}
        for idx, pos, field in headers:
            if field not in self._detail_fields:
                continue

            ci, cp, cv = find_value(pos, idx)
            data[self._detail_fields[field]] = cv

        return data

    def _read_transactions(self, texts, rows):
        def replace_tabs(t):
            return re.sub(r'\t', ' ', t)

        def values(idxlist):
            return [texts[idx][1] for idx in idxlist]

        def get_lines(idxlist):
            lines = []
            for line in values(idxlist):
                line = line.strip()
                if line.endswith('<br>'):
                    line = line[:-4]
                line = list(map(replace_tabs, re.split('<br>', line)))
                lines += line
            return lines

        def combine(textlist):
            return ' '.join(textlist)

        data = []
        for row in rows:
            tanggal = self._stripws(self._stripbr(combine(values(row['cols'][0]))))
            rincian = get_lines(row['cols'][1])
            catatan = get_lines(row['cols'][2])
            jumlah = get_lines(row['cols'][3])

            d = {}

            d['date'] = parse_date(tanggal)
            d['description'] = rincian[0]
            d['reference'] = None
            if len(rincian) > 2:
                d['reference'] = rincian[1]

            d['id'] = rincian[-1].split('|')[0].strip()
            d['category'] = rincian[-1].split('|')[1].strip()
            d['type'] = catatan[-1]
            d['note'] = None
            if len(catatan) > 1:
                d['note'] = catatan[0]
            d['amount'] = parse_number(jumlah[0])

            curr_txn, curr_acc, rate = parse_currency_exchange(jumlah[-1])
            d['currency'] = curr_acc
            d['transaction_currency'] = curr_txn
            d['rate'] = rate

            data.append(d)

        return data

    def _find_rows(self, texts, cols):
        col0 = []
        for idx, col in cols.items():
            if col != 0:
                continue
            x, y, w, h = texts[idx][0]
            tt = texts[idx][1]
            col0.append((idx, (y, h)))

        col0 = sorted(col0, key=lambda r: r[1][0])

        dates = []
        row = 0
        while row < len(col0):
            idx, pos = col0[row]
            y, h = pos
            row += 1

            tt = texts[idx][1]
            if row == 1:
                if not tt.startswith('TANGGAL'): # FIXME self._table_headers[0]):
                    raise Exception('Cannot found "{}"'.format(self._table_headers[0]))
                continue

            if re.search(r'\d\d:\d\d', tt):
                dates.append((idx, y, [idx], tt))
                continue

            idx2, _ = col0[row]
            row += 1

            tt2 = texts[idx2][1]
            if not re.search(r'\d\d:\d\d', tt2):
                raise Exception('could not find time')

            dates.append((idx, y, [idx, idx2], tt + ' ' + tt2))

        rows = []
        maxh = 0
        for i, date in enumerate(dates):
            idx, y, idxlist, t = date

            cc = defaultdict(list)
            rows.append(dict(
                    row=i,
                    cols=cc,
                    y=y,
                    height=0,
                    last=True
                ))

            if len(rows) > 1:
                h = rows[-1]['y'] - rows[-2]['y']
                maxh = max(maxh, h)

                rows[-2]['last'] = False
                rows[-2]['height'] = h

        rows[-1]['height'] = maxh

        margin = 2
        for idx, col in cols.items():
            x, y, w, h = texts[idx][0]
            tt = texts[idx][1]

            found = False
            for row in rows:
                if y >= row['y'] - margin and y < row['y'] + row['height']:
                    row['cols'][col].append(idx)
                    found = True
                    break

        def cmp_y(a, b):
            _, y1, _, _ = texts[a][0]
            _, y2, _, _ = texts[b][0]
            return y1 - y2

        for row in rows:
            for i in range(len(row['cols'])):
                row['cols'][i] = sorted(row['cols'][i], key=cmp_to_key(cmp_y))

        return rows

    def _find_content(self, texts, ymin, ymax):
        content = []
        for idx, t in enumerate(texts):
            x, y, w, h = t[0]
            if y < ymin:
                continue
            if y >= ymax:
                continue

            content.append(idx)

        return content

    def _find_columns(self, texts, content):
        def cmp_interval(a, b):
            x, y, w, h = a[1]
            x2, y2, w2, h2 = b[1]

            if x != x2:
                return x - x2

            return (x+w) - (x2+w2)

        intervals = []

        for idx in content:
            t = texts[idx]
            x, y, w, h = t[0]
            tt = t[1]
            intervals.append((idx, tuple(map(int, [x, y, w, h]))))

        intervals = sorted(intervals, key=cmp_to_key(cmp_interval))

        merged = []
        for interval in intervals:
            idx = interval[0]
            x, y, w, h = interval[1]

            if not merged:
                merged.append(([idx], (x, y, w, h)))
                continue

            idx0 = merged[-1][0]
            x0, y0, w0, h0 = merged[-1][1]
            if x0 + w0 < x:
                merged.append(([idx], (x, y, w, h)))
                continue

            merged[-1] = (idx0 + [idx], (x0, y0, max(x0+w0, x+w) - x0, h0))

        cols = {}
        for i, item in enumerate(merged):
            idxlist, bb = item
            for idx in idxlist:
                cols[idx] = i

            for idx in idxlist:
                tt = texts[idx][1]

            for idx in idxlist:
                tt = texts[idx][1]
                x, y, w, h = texts[idx][0]

        return cols

    def _get_table_boundaries(self, texts):
        ymin = 0
        ymax = 0
        for t in texts:
            x, y, w, h = t[0]
            s = t[1]
            s = re.sub(r'\s+', ' ', s.replace('<br>', '').strip())
            for c in self._table_headers:
                if s.startswith(c):
                    if ymin == 0:
                        ymin = y
                    ymin = min(ymin, y)

            for c in self._footer_markers:
                if s.startswith(c):
                    if ymax == 0:
                        ymax = y
                    ymax = min(ymax, y)

        return ymin, ymax

    def _cmp_position(self, a, b):
        y1 = a[0][1]
        y2 = b[0][1]
        if y1 != y2:
            return y1 - y2

        x1 = a[0][0]
        x2 = b[0][0]
        return x1 - x2

    def _get_texts(self, page):
        outfp = io.StringIO()

        res = PDFResourceManager(caching=False)
        laparams = LAParams()
        device = Collector(res, outfp, codec='utf-8', laparams=laparams)
        interpreter = PDFPageInterpreter(res, device)
        interpreter.process_page(page)
        device.close()

        return device._texts

    def _merge_details(self, a, b):
        if a is None:
            return b
        return a

    def _merge_transactions(self, a, b):
        return a + b

if __name__ == '__main__':
    import sys
    from pprint import pprint

    inp = sys.argv[1]
    with open(inp, 'rb') as f:
        p = Parser()
        data = p.parse(f)
        pprint(data.details)
        pprint(data.transactions)


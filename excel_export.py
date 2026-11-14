"""Minimal dependency-free OOXML workbook writer for tabular research exports.
Uses inline strings and shared formatting; guards spreadsheet formula injection.
"""
import io, zipfile, datetime
from xml.sax.saxutils import escape, quoteattr

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'

def _cell(v, ref, head=False):
    sty=' s="1"' if head else ''
    if v is None: return f'<c r="{ref}"{sty}/>'
    if isinstance(v,bool):return f'<c r="{ref}"{sty} t="b"><v>{int(v)}</v></c>'
    if isinstance(v,(int,float)) and not isinstance(v,bool):return f'<c r="{ref}"{sty}><v>{v}</v></c>'
    s=str(v)
    if s.startswith(('=','+','-','@','\t','\r','\n')):s="'"+s
    s=escape(s)
    return f'<c r="{ref}"{sty} t="inlineStr"><is><t xml:space="preserve">{s}</t></is></c>'

def _col(index):
    t=''
    while index:index,r=divmod(index-1,26);t=chr(65+r)+t
    return t

def _sheet(headers,rows):
    vals=[list(headers)]+[list(r) for r in rows]
    ncols=len(headers)
    cols=''.join(f'<col min="{i+1}" max="{i+1}" width="{min(46,max(13,len(str(h))+4))}" customWidth="1"/>' for i,h in enumerate(headers))
    records=[]
    for ridx,row in enumerate(vals,1):
        records.append('<row r="%d"%s>'%(ridx,' ht="26" customHeight="1"' if ridx==1 else '')+''.join(_cell(v,f'{_col(c)}{ridx}',head=ridx==1) for c,v in enumerate(row,1))+'</row>')
    dim=f'A1:{_col(ncols)}{max(1,len(vals))}'
    xml=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{NS}"><dimension ref="{dim}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="16"/><cols>{cols}</cols><sheetData>{''.join(records)}</sheetData><autoFilter ref="{dim}"/></worksheet>'''
    return xml.encode('utf-8')

def create_workbook(sheets):
    """sheets list of tuples: (title, headers, iterable_of_rows)"""
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED) as z:
        names=''.join(f'<sheet name={quoteattr(title)} sheetId="{i}" r:id="rId{i}"/>' for i,(title,_,__) in enumerate(sheets,1))
        z.writestr('xl/workbook.xml',f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{names}</sheets></workbook>''')
        wsrels=''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))
        z.writestr('xl/_rels/workbook.xml.rels',f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{wsrels}<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''')
        z.writestr('xl/styles.xml',f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{NS}"><fonts count="2"><font><sz val="11"/><name val="Inter"/><color rgb="FF19253A"/></font><font><b/><sz val="11"/><name val="Inter"/><color rgb="FFFFFFFF"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFCB0017"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''')
        ct=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))
        z.writestr('[Content_Types].xml',f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{ct}</Types>''')
        z.writestr('_rels/.rels','''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        for i,(_,headers,rows) in enumerate(sheets,1):z.writestr(f'xl/worksheets/sheet{i}.xml',_sheet(headers,rows))
    return b.getvalue()

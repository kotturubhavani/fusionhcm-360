"""Run PDF parsing in a time-limited child process; no files or OCR."""
import io
import sys
import warnings
from pypdf import PdfReader

def extract(content):
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        reader=PdfReader(io.BytesIO(content),strict=True)
        if reader.is_encrypted or len(reader.pages)>30:raise ValueError()
        result=[]
        for page in reader.pages:
            value=page.extract_text() or ''
            result.append(value)
            if sum(map(len,result))>40000:raise ValueError()
        text='\n\n'.join(result)
        if len(text.strip())<30:raise ValueError()
        return text

if __name__=='__main__':
    try:
        content=sys.stdin.buffer.read(5*1024*1024+1)
        if len(content)>5*1024*1024:raise ValueError()
        sys.stdout.buffer.write(extract(content).encode('utf-8'))
    except Exception:sys.exit(2)

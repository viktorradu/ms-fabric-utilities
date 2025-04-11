import os
import zipfile

file_in = 'template.pbit'

inpath = os.path.abspath(file_in)

outpath = os.path.abspath(f'template-edited.pbit')
with zipfile.ZipFile(inpath) as inzip, zipfile.ZipFile(outpath, 'w', compression=zipfile.ZIP_DEFLATED) as outzip:
    for inzipinfo in inzip.infolist():
        with inzip.open(inzipinfo) as infile:

            # Check if file needs to nbe modified
            if inzipinfo.filename == "DataModelSchema":

                # Modify the file content
                content = infile.read().decode('utf-16') 
                content = content.replace('Source = SomeParameter', 'Source = SomeOtherParameter')

                outzip.writestr(inzipinfo.filename, content.encode('utf-16')[2:])
            else:
                outzip.writestr(inzipinfo.filename, infile.read())
    inzip.close()
    outzip.close()
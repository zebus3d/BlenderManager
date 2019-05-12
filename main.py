from rws import ReaderWritterSettigns

# Probando el reader de settings:
rw = ReaderWritterSettigns()
# voy a leer en la seccion defaults la opcion BuilderServer:
rw.reader('defaults', 'BuilderServer')

rw.add_section('test') 
rw.add_option('test', 'pepe', 'volador')
rw.write_options()
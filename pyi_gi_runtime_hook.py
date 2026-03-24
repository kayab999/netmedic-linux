import os, sys, gi
bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath('.'))
typelib_path = os.path.join(bundle_dir, 'gi_typelibs')
if os.path.exists(typelib_path):
    os.environ['GI_TYPELIB_PATH'] = typelib_path
if 'LD_LIBRARY_PATH' in os.environ:
    del os.environ['LD_LIBRARY_PATH']

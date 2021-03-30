# Copyright (c) 2008-2012 AJ
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# <pep8 compliant>

bl_info = {
    'name': 'GunZ: The Duel/The Second Duel, RaiderZ ELU/ANI/XML formats',
    'author': 'AJ',
    'blender': (2, 5, 7),
    'location': 'File > Import',
    'description': 'Import ELU/ANI data',
    'warning': '',
    'wiki_url': '',
    'tracker_url': '',
    'support': 'COMMUNITY',
    'category': 'Import-Export'
}

# To support reload properly, try to access a package var, if it's there, reload everything
if 'bpy' in locals():
    import imp

    if 'import_elu' in locals():
        imp.reload(import_elu)

#    if 'import_ani' in locals():
#        imp.reload(import_ani)


import os
import bpy
import bpy_extras


ELU_FILE_EXTENSION = '*.elu'

#
#ANI_FILE_EXTENSION = '*.ani'


class BipMeshSettings(bpy.types.PropertyGroup):
    raw_world_matrix = bpy.props.FloatVectorProperty(
        name='raw_world_matrix',
        description='Raw World Matrix',
        default=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        options={'HIDDEN'},
        size=16,
        subtype='MATRIX'
    )

    raw_local_matrix = bpy.props.FloatVectorProperty(
        name='raw_local_matrix',
        description='Raw Local Matrix',
        default=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        options={'HIDDEN'},
        size=16,
        subtype='MATRIX'
    )

    parent_name = bpy.props.StringProperty(
        name="parent_name",
        description="Parent Name",
        default="",
        options={'HIDDEN'}
    )

    is_bip = bpy.props.BoolProperty()

#    is_parent_bip = bpy.props.BoolProperty()


class ImportELU(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    '''Load a ELU file'''

    bl_idname = 'import_mesh.elu'

    bl_label = 'Import ELU'

    bl_options = {
        'UNDO'
    }

    files = bpy.props.CollectionProperty(
        name='File Path',
        description='File path used for importing the ELU file',
        type=bpy.types.OperatorFileListElement
    )

    directory = bpy.props.StringProperty()

    filter_glob = bpy.props.StringProperty(
        default=ELU_FILE_EXTENSION,
        options={
            'HIDDEN'
        }
    )

    def execute(self, context):
        paths = [os.path.join(self.directory, f.name) for f in self.files]

        if not paths:
            paths.append(self.filepath)

        from . import import_elu

        return import_elu.load_from_path(paths[0], context)

#
#class ImportANI(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
#    '''Load a ANI file'''
#
#    bl_idname = 'import_animation.ani'
#
#    bl_label = 'Import ANI'
#
#    bl_options = {
#        'UNDO'
#    }
#
#    files = bpy.props.CollectionProperty(
#        name='File Path',
#        description='File path used for importing the ANI file',
#        type=bpy.types.OperatorFileListElement
#    )
#
#    directory = bpy.props.StringProperty()
#
#    filter_glob = bpy.props.StringProperty(
#        default=ANI_FILE_EXTENSION,
#        options={
#            'HIDDEN'
#        }
#    )
#
#    def execute(self, context):
#        paths = [os.path.join(self.directory, f.name) for f in self.files]
#
#        if not paths:
#            paths.append(self.filepath)
#
#        from . import import_ani
#
#        return import_ani.load_from_path(paths[0], context)


def menu_func_import(self, context):
    self.layout.operator(ImportELU.bl_idname, text="GunZ: The Duel/The Second Duel, RaiderZ (.elu)")
#
#    self.layout.operator(ImportANI.bl_idname, text="Gunz: The Duel (.ani)")


def register():
    bpy.utils.register_class(BipMeshSettings)

    bpy.types.Mesh.bip_settings = bpy.props.PointerProperty(type=BipMeshSettings)

    bpy.utils.register_module(__name__, True)

    bpy.types.INFO_MT_file_import.append(menu_func_import)


def unregister():
    del bpy.types.Mesh.bip_settings

    bpy.utils.unregister_class(BipMeshSettings)

    bpy.utils.unregister_module(__name__)

    bpy.types.INFO_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
    register()
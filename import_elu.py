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


import bpy
import bpy_extras
import io
import logging
import math
import mathutils
import os
import re
import struct


def enum(**attrs):
    return type('Enum', (frozenset,), attrs)(attrs.values())


ELU_MAGIC = 0x0107F060


ELU_VERSIONS = enum(
# GunZ: The Duel
    x11=0x11, 
    x5001=0x5001,
    x5002=0x5002,
    x5003=0x5003,
    x5004=0x5004,
    x5005=0x5005,
    x5006=0x5006,
    x5007=0x5007,
# GunZ: The Second Duel, RaiderZ
    x5008=0x5008,
    x500A=0x500A,
    x500B=0x500B,
    x500C=0x500C,
    x500E=0x500E,
    x500F=0x500F,
    x5010=0x5010,
    x5011=0x5011
)


NAME_LENGTH = 40


PATH_LENGTH = 256


FACE_VERTEX_COUNT = 3


BONE_INFLUENCE_COUNT = 4


SMOOTH_GROUP_COUNT = 32


ELU_BIP_REGEX = r'^Bip\d{2,}\s*(?P<side>L|R)?\s*(?P<name>[a-zA-Z]+)?(?P<index>\d+)?(?P<nub>[a-zA-Z]+)?$'


ELU_BIP_PROGRAM = re.compile(ELU_BIP_REGEX)


def elu_to_blender_name(name):
    def blend(match):
        if match.group('name') is not None:
            blend_format = "ZBip_{name}"
        else:
            blend_format = "ZBip_Root"

        if match.group('nub') is not None:
            blend_format += "_{nub}"

        if match.group('side') is not None:
            blend_format += ".{side}"

        if match.group('index') is not None:
            if len(match.group('index')) > 1 and \
               int(match.group('index')) < 10:
                blend_format += ".1{index:0>3}"
            elif int(match.group('index')) > 0:
                blend_format += ".{index:0>3}"

        return blend_format.format(**match.groupdict())

    return ELU_BIP_PROGRAM.subn(blend, name)


def load_elu_mesh_a(elu, version):
    '''GunZ: The Duel'''
    name = elu.read(NAME_LENGTH)

    parent_name = elu.read(NAME_LENGTH)

    mesh_name, is_bip = elu_to_blender_name(str(name, encoding='ascii').rstrip('\0'))

    parent_mesh_name, is_parent_bip = elu_to_blender_name(str(parent_name, encoding='ascii').rstrip('\0'))

    wm = struct.unpack('<16f', elu.read(64))

    world_matrix = mathutils.Matrix((
        (wm[0], wm[4], wm[8], wm[12]),
        (wm[2], wm[6], wm[10], wm[14]),
        (wm[1], wm[5], wm[9], wm[13]),
        (wm[3], wm[7], wm[11], wm[15])
    ))

    if version > ELU_VERSIONS.x11:
        sx, sy, sz = struct.unpack('<3f', elu.read(12))

        scale = mathutils.Vector((sx, sz, sy))
    else:
        scale = mathutils.Vector((1.0, 1.0, 1.0))

    scale_matrix = mathutils.Matrix.Scale(1.0, 4, scale)

    if version > ELU_VERSIONS.x5002:
        rx, ry, rz, ra = struct.unpack('<4f', elu.read(16))

        rotation_matrix = mathutils.Matrix.Rotation(ra, 4, mathutils.Vector((rx, rz, ry)))

        psx, psy, psz, psa = struct.unpack('<4f', elu.read(16))

        pivot_scale_matrix = mathutils.Matrix.Rotation(psa, 4,  mathutils.Vector((psx, psz, psy)))

        pm = struct.unpack('<16f', elu.read(64))

        pivot_matrix = mathutils.Matrix((
            (pm[0], pm[4], pm[8], pm[12]),
            (pm[2], pm[6], pm[10], pm[14]),
            (pm[1], pm[5], pm[9], pm[13]),
            (pm[3], pm[7], pm[11], pm[15])
        ))

    vertex_count = struct.unpack('<I', elu.read(4))[0]

    vertices = []

    for i in range(vertex_count):
        x, y, z = struct.unpack('<3f', elu.read(12))

        vertices.append((x, y, z))

    face_count = struct.unpack('<I', elu.read(4))[0]

    faces = []

    uv_faces = []

    smooth_groups = [[] for i in range(SMOOTH_GROUP_COUNT)]

    for i in range(face_count):
        v1, v2, v3 = struct.unpack('<3I', elu.read(12))

        if v3 == 0:
            faces.append((v3, v1, v2))
        else:
            faces.append((v1, v2, v3))

        face_uvs = []

        for j in range(FACE_VERTEX_COUNT):
            u, v, w = struct.unpack('<3f', elu.read(12))

            face_uvs.append((u, 1.0 - v)) # flip v, drop w

        if v3 == 0:
            uv_faces.append((face_uvs[2], face_uvs[0], face_uvs[1]))
        else:
            uv_faces.append(tuple(face_uvs))

        elu.seek(4, os.SEEK_CUR) # material index: 1 unsigned long integer

        if version > ELU_VERSIONS.x5001:
            smooth_group_index = struct.unpack('<I', elu.read(4))[0]

            smooth_groups[smooth_group_index].extend([v1, v2, v3])

    if version > ELU_VERSIONS.x5004:
        # face normals, skipped, it's not possible to set with blender api
        for i in range(face_count):
            elu.seek(12, os.SEEK_CUR) # face normal: 3 single precision float

            # vertex normals, skipped, recalculated using calc_normals method
            for j in range(FACE_VERTEX_COUNT):
                elu.seek(12, os.SEEK_CUR) # vertex normal: 3 single precision floats

    vertex_colors = []

    if version > ELU_VERSIONS.x5004:
        vertex_color_count = struct.unpack('<I', elu.read(4))[0]

        for i in range(vertex_color_count):
            r, g, b = struct.unpack('<3f', elu.read(12))

            vertex_colors.append((r, g, b))

    material_index, \
    bone_influence_count = struct.unpack('<2I', elu.read(8))

    weight_groups = {}

    for i in range(bone_influence_count):
        bone_names = []

        for j in range(BONE_INFLUENCE_COUNT):
            name = elu.read(NAME_LENGTH)

            bone_name = elu_to_blender_name(str(name, encoding='ascii').rstrip('\0'))[0]

            if len(bone_name) > 0:
                bone_names.append(bone_name)

        bone_weights = [w for w in struct.unpack('<4f', elu.read(16)) if w > 0.0]

        elu.seek(16, os.SEEK_CUR) # parent indices: 4 unsigned long integers

        elu.seek(4, os.SEEK_CUR) # weight count: 1 unsigned long integer

        for j in range(BONE_INFLUENCE_COUNT):
            elu.seek(12, os.SEEK_CUR) # offset vector: 3 single precision floats

        for j, bone_weight in enumerate(bone_weights):
            bone_name = bone_names[j]

            if bone_names[j] not in weight_groups:
                weight_groups[bone_name] = {}

            if bone_weight not in weight_groups[bone_name]:
                weight_groups[bone_name][bone_weight] = []

            weight_groups[bone_name][bone_weight].append(i)

    mesh_object = None

    if mesh_name not in bpy.data.meshes and \
       len(vertices) > 0 and \
       len(faces) > 0:
        mesh = bpy.data.meshes.new(mesh_name)

        mesh.bip_settings.is_bip = bool(is_bip)
        mesh.bip_settings.raw_world_matrix = [x for col in world_matrix.col[:] for x in col]

        local_matrix = mathutils.Matrix()
        local_matrix.identity()

        if parent_mesh_name in bpy.data.meshes:
            parent_mesh = bpy.data.meshes[parent_mesh_name]

            parent_world_matrix = parent_mesh.bip_settings.raw_world_matrix

            inverse_parent_world_matrix = parent_world_matrix.inverted()

            local_matrix = inverse_parent_world_matrix * world_matrix
        else:
            local_matrix = world_matrix

        mesh.bip_settings.raw_local_matrix = [x for col in local_matrix.col[:] for x in col]

        mesh.from_pydata(vertices, [], faces)

        image = None

        material_name = "z_material.{0:03}".format(material_index)

        if material_name in bpy.data.materials:
            material = bpy.data.materials[material_name]

            mesh.materials.append(material)

            texture = material.active_texture

            if texture is not None and \
               texture.type == 'IMAGE':
                image = texture.image

        if len(uv_faces) > 0:
            texture_face_layer = mesh.uv_textures.new('z_uv_texture')

            #texture_face_layer.active = True

            for i, texture_face in enumerate(texture_face_layer.data):
                if image is not None:
                    texture_face.image = image

            uv_layer = mesh.uv_layers.active.data[:]

            for fi, ply in enumerate(mesh.polygons):
                uv_layer[ply.loop_start].uv = uv_faces[fi][0]
                uv_layer[ply.loop_start + 1].uv = uv_faces[fi][1]
                uv_layer[ply.loop_start + 2].uv = uv_faces[fi][2]

        cloth = [[], [], {}]

        for i, (hold, collision, weight) in enumerate(vertex_colors):
            weight = 1.0 - weight

            if hold > 0.0:
                cloth[0].append(i)

            if collision > 0.0:
                cloth[1].append(i)

            if weight > 0.0:
                if weight not in cloth[2]:
                    cloth[2][weight] = []

                cloth[2][weight].append(i)

        mesh.show_double_sided = False
        mesh.show_normal_face = True
        mesh.show_normal_vertex = True

        mesh.calc_normals()

        mesh.validate()

        mesh.update()

        mesh_object = bpy.data.objects.new(mesh_name, mesh)

        if len(vertex_colors) > 0:
            cloth_modifier = mesh_object.modifiers.new('z_cloth', 'CLOTH')

            cloth_modifier.collision_settings.use_self_collision = True

            if len(cloth[0]) > 0:
                pinning_group = mesh_object.vertex_groups.new('z_cloth_pin')

                pinning_group.add(cloth[0], 1.0, 'ADD')

                cloth_modifier.settings.use_pin_cloth = True
                cloth_modifier.settings.vertex_group_mass = 'Zpin'

            stiff_group = mesh_object.vertex_groups.new('z_cloth_stiff')

            for w, v in cloth[2].items():
                stiff_group.add(v, w, 'ADD')

            cloth_modifier.settings.use_stiffness_scale = True
            cloth_modifier.settings.structural_stiffness = 0.5
            cloth_modifier.settings.structural_stiffness_max = 1.0
            cloth_modifier.settings.vertex_group_structural_stiffness = 'z_cloth_stiff'

        for i, vertices in enumerate(smooth_groups):
            if len(vertices) > 0:
                smooth_group_name = "z_smooth.{0:03}".format(i)

                smooth_group = mesh_object.vertex_groups.new(smooth_group_name)

                smooth_group.add(vertices, 1.0, 'ADD')

                smooth_modifier = mesh_object.modifiers.new(smooth_group_name, 'SMOOTH')

                smooth_modifier.factor = 0.0
                smooth_modifier.vertex_group = smooth_group_name

        for bone_name, bone_weights in weight_groups.items():
            weight_group = mesh_object.vertex_groups.new(bone_name)

            for bone_weight, vertices in bone_weights.items():
                weight_group.add(vertices, bone_weight, 'ADD')
    else:
        mesh_object = bpy.data.objects.new(mesh_name, None) # Empty

    if mesh_object is not None:
        #mesh_object.show_x_ray = bool(is_bip)

        if parent_mesh_name in bpy.data.objects:
            mesh_object.parent = bpy.data.objects[parent_mesh_name]

        mesh_object.matrix_world = world_matrix

        scene = bpy.context.scene

        scene.objects.link(mesh_object)

        scene.update()

    return mesh_object


def load_elu_mesh_b(elu, version):
    '''GunZ: The Second Duel and RaiderZ'''
    name_length = struct.unpack('<I', elu.read(4))[0]

    name = elu.read(name_length)

    parent_name_length = struct.unpack('<I', elu.read(4))[0]

    parent_name = elu.read(parent_name_length)

    mesh_name, is_bip = elu_to_blender_name(str(name, encoding='ascii').rstrip('\0'))

    parent_mesh_name, is_parent_bip = elu_to_blender_name(str(parent_name, encoding='ascii').rstrip('\0'))

    logging.info("Loading mesh: %s [%s], parent: %s [%s]", mesh_name, bool(is_bip), parent_mesh_name if parent_name_length > 0 else 'NIL', bool(is_parent_bip))

    parent_mesh_index = struct.unpack('<I', elu.read(4))[0]

    if version == ELU_VERSIONS.x5008:
        elu.seek(20, os.SEEK_CUR) # unknown
    else: 
        elu.seek(8, os.SEEK_CUR) # unknown

    lm = struct.unpack('<16f', elu.read(64))

    local_matrix = mathutils.Matrix((
        (lm[0], lm[4], lm[8], lm[12]),
        (lm[1], lm[5], lm[9], lm[13]),
        (lm[2], lm[6], lm[10], lm[14]),
        (lm[3], lm[7], lm[11], lm[15])
    ))

    if version >= ELU_VERSIONS.x500E and \
       version <= ELU_VERSIONS.x5010:
        elu.seek(12, os.SEEK_CUR) # unknown
    elif version > ELU_VERSIONS.x5008:
        elu.seek(4, os.SEEK_CUR) # unknown: 1 single precision floats

    vertex_position_count = struct.unpack('<I', elu.read(4))[0]

    vertex_positions = []

    logging.debug("loop %x", elu.tell())

    for i in range(vertex_position_count):
        px, py, pz = struct.unpack('<3f', elu.read(12))

        vertex_positions.append((px, py, pz))

    vertex_normal_count = struct.unpack('<I', elu.read(4))[0]

    vertex_normals = []

    logging.debug("looop %x", elu.tell())

    for i in range(vertex_normal_count):
        nx, ny, nz = struct.unpack('<3f', elu.read(12))

        vertex_normals.append((nx, ny, nz))

    unknown_count = struct.unpack('<I', elu.read(4))[0]

    skipped_length = 12

    if version > ELU_VERSIONS.x500E:
        skipped_length = 16

    logging.debug("loooop %x", elu.tell())

    for i in range(unknown_count):
        elu.seek(skipped_length, os.SEEK_CUR) # unknown: 3 single precision floats

    unknown_count = struct.unpack('<I', elu.read(4))[0]
    if version > ELU_VERSIONS.x500E and \
       unknown_count != 0:
        logging.warning("Oh no! %x", elu.tell())

        unknown_count = 0 # fix?

    logging.debug("looooop %x", elu.tell())

    for i in range(unknown_count):
        elu.seek(12, os.SEEK_CUR) # unknown: 3 single precision floats

    vertex_texcoord_count = struct.unpack('<I', elu.read(4))[0]

    vertex_texcoords = []

    logging.debug("loooooop %x", elu.tell())

    for i in range(vertex_texcoord_count):
        u, v, w = struct.unpack('<3f', elu.read(12))

        vertex_texcoords.append((u, 1.0 - v)) # flip v, drop w

    if version >= ELU_VERSIONS.x500E and \
       version != ELU_VERSIONS.x5010:
        unknown_count = struct.unpack('<I', elu.read(4))[0]

        logging.debug("looooooop+ %x", elu.tell())

        for i in range(unknown_count):
            elu.seek(12, os.SEEK_CUR) # unknown: 3 single precision floats

    unknown_count0 = struct.unpack('<I', elu.read(4))[0]
    face_count = unknown_count0 # version 500A

    logging.debug("loooooooop %x", elu.tell())

    if version > ELU_VERSIONS.x500A:
        if unknown_count0 > 0:
            elu.seek(8, os.SEEK_CUR) # unknown, 2 unsigned long integers

            for i in range(unknown_count0):
                unknown_count1 = struct.unpack('<I', elu.read(4))[0] # totaled = 1st unsigned long integer

                skipped_length = 12 # unknown: 1 unsigned short, 1 unsigned long, 3 unsigned short integers

                if version < ELU_VERSIONS.x500E:
                    skipped_length = 10 # unknown: 5 unsigned short integers

                for j in range(unknown_count1):
                    elu.seek(skipped_length, os.SEEK_CUR)
                elu.seek(2, os.SEEK_CUR) # unknown
    else:
        for i in range(unknown_count0):
            elu.seek(32, os.SEEK_CUR) # unknown

    unknown_count = struct.unpack('<I', elu.read(4))[0]

    logging.debug("looooooooop %x", elu.tell())

    for i in range(unknown_count):
        elu.seek(12, os.SEEK_CUR) # unknown
    elu.seek(4, os.SEEK_CUR) # unknown: 1 unsigned long integer

    blend_vertex_count = struct.unpack('<I', elu.read(4))[0]
    if version < ELU_VERSIONS.x500E and \
       blend_vertex_count != 0:
        logging.warning("Oh no! %x", elu.tell())

        blend_vertex_count = 0 # fix?

    bone_influences = {}
    logging.debug("loooooooooop %x", elu.tell())

    for i in range(blend_vertex_count):
        bone_influence_count = struct.unpack('<I', elu.read(4))[0]
        for j in range(bone_influence_count):
            elu.seek(2, os.SEEK_CUR) # unknown

            bone_index, bone_weight = struct.unpack('<Hf', elu.read(6))

            if bone_weight > 0.0:
                if bone_index not in bone_influences:
                    bone_influences[bone_index] = {}

                if bone_weight not in bone_influences[bone_index]:
                    bone_influences[bone_index][bone_weight] = []

                if i not in bone_influences[bone_index][bone_weight]:
                    bone_influences[bone_index][bone_weight].append(i)

    unknown_count = struct.unpack('<I', elu.read(4))[0]
    if version < ELU_VERSIONS.x500E and \
       unknown_count != 0:
        logging.warning("Oh no! %x", elu.tell())

        unknown_count = 0 # fix?

    logging.debug("looooooooooop %x", elu.tell())

    for i in range(unknown_count):
        elu.seek(64, os.SEEK_CUR) # unknown: 16 single precision floats = matrix

    for i in range(unknown_count):
        elu.seek(2, os.SEEK_CUR) # unknown: 1 unsigned short integer

    vertex_count = struct.unpack('<I', elu.read(4))[0]

    vertex_indices = []

    logging.debug("loooooooooooop %x", elu.tell())

    for i in range(vertex_count):
        vertex_position_index = vertex_normal_index = vertex_texcoord_index = vertex_unknown0_index = vertex_unknown1_index = 0

        if version < ELU_VERSIONS.x500E:
            vertex_position_index, \
            vertex_normal_index, \
            vertex_texcoord_index, \
            vertex_unknown0_index, \
            vertex_unknown1_index = struct.unpack('<5H', elu.read(10))
        elif version == ELU_VERSIONS.x500E:
            vertex_position_index, \
            vertex_normal_index, \
            vertex_unknown1_index, \
            vertex_unknown0_index, \
            vertex_texcoord_index = struct.unpack('<2HI2H', elu.read(12))
        else:
            vertex_position_index, \
            vertex_normal_index, \
            vertex_texcoord_index, \
            vertex_unknown0_index, \
            vertex_unknown1_index = struct.unpack('<2HI2H', elu.read(12))

        vertex_indices.append((vertex_position_index, vertex_normal_index, vertex_texcoord_index, vertex_unknown0_index, vertex_unknown1_index))

    if version > ELU_VERSIONS.x500A:
        elu.seek(4, os.SEEK_CUR) # unknown: 1 unsigned long integer

    face_index_count = 0

    if version > ELU_VERSIONS.x500A:
        face_index_count = struct.unpack('<I', elu.read(4))[0]

        face_count = int(face_index_count / 3)

    faces = []

    logging.debug("looooooooooooop %x", elu.tell())

    for i in range(face_count):
        face = [[], [], []]
    
        for y in struct.unpack('<3H', elu.read(6)):
            vertex_position_index = vertex_indices[y][0]
            vertex_normal_index = vertex_indices[y][1]
            vertex_texcoord_index = vertex_indices[y][2]

            face[0].append(vertex_position_index)
            face[1].append(vertex_normal_index)
            face[2].append(vertex_texcoord_index)
    
        faces.append(face)

    unknown_count = struct.unpack('<I', elu.read(4))[0]

    logging.debug("loooooooooooooop %x", elu.tell())

    for i in range(unknown_count):
        elu.seek(12, os.SEEK_CUR) # unknown

    if version >= ELU_VERSIONS.x500E:
        elu.seek(24, os.SEEK_CUR) # unknown

    mesh_object = None

    if mesh_name not in bpy.data.meshes:
        mesh = bpy.data.meshes.new(mesh_name)

        if mesh is not None:
            mesh.bip_settings.raw_local_matrix = [x for col in local_matrix.col[:] for x in col]

            if len(vertex_positions) > 0 and \
               len(faces) > 0:
                mesh.bip_settings.is_bip = False

                mesh.from_pydata(vertex_positions, [], [f[0] for f in faces])

                if version >= ELU_VERSIONS.x500B:
                    texture_face_layer = mesh.uv_textures.new('z_uv_texture')

                    for i, texture_face in enumerate(texture_face_layer.data):
                        pass # to-do: set uv image

                    uv_layer = mesh.uv_layers.active.data[:]

                    for fi, ply in enumerate(mesh.polygons):
                        uv_layer[ply.loop_start].uv = vertex_texcoords[faces[fi][2][0]]
                        uv_layer[ply.loop_start + 1].uv = vertex_texcoords[faces[fi][2][1]]
                        uv_layer[ply.loop_start + 2].uv = vertex_texcoords[faces[fi][2][2]]

                mesh.show_double_sided = False
                mesh.show_normal_face = True
                mesh.show_normal_vertex = True

                mesh.calc_normals()
            else:
                mesh.bip_settings.is_bip = True

                mesh.from_pydata(
                    [
                        (-0.5, 0.5, -0.5),
                        (-0.5, 0.5, 0.5),
                        (0.5, 0.5, 0.5),
                        (0.5, 0.5, -0.5),
                        (-0.5, -0.5, -0.5),
                        (-0.5, -0.5, 0.5),
                        (0.5, -0.5, 0.5),
                        (0.5, -0.5, -0.5)
                    ],
                    [
                        (0, 1),
                        (1, 2),
                        (2, 3),
                        (3, 0),
                        (4, 5),
                        (5, 6),
                        (6, 7),
                        (7, 4),
                        (0, 4),
                        (1, 5),
                        (2, 6),
                        (3, 7)
                    ],
                    []
                )

            mesh.validate()

            mesh.update()

            mesh_object = bpy.data.objects.new(mesh_name, mesh)

            if mesh_object is not None:
                if version > ELU_VERSIONS.x500B:
                    for bone_index, bone_weights in bone_influences.items():
                        weight_group = mesh_object.vertex_groups.new(str(bone_index))
    
                        for bone_weight, bone_vertices in bone_weights.items():
                            weight_group.add(bone_vertices, bone_weight, 'ADD')

                if parent_mesh_index != 0xFFFFFFFF and \
                   parent_mesh_name in bpy.data.objects:
                    mesh_object.parent = bpy.data.objects[parent_mesh_name]

                mesh_object.matrix_local = local_matrix

                scene = bpy.context.scene

                if scene is not None:
                    scene.objects.link(mesh_object)

                    scene.update()
    else:
        logging.error("WTF!")

        mesh_object = None

    return mesh_object


def load_elu_mesh(elu, version):
    mesh_object = None

    if version < ELU_VERSIONS.x5008:
        mesh_object = load_elu_mesh_a(elu, version) #
    else:
        mesh_object = load_elu_mesh_b(elu, version)

    return mesh_object


def load_elu_texture(elu, version):
    '''GunZ: The Duel'''
    name0 = None
    name1 = None

    if version < ELU_VERSIONS.x5006:
        name0 = elu.read(NAME_LENGTH)
        name1 = elu.read(NAME_LENGTH)
    else:
        name0 = elu.read(PATH_LENGTH)
        name1 = elu.read(PATH_LENGTH)

    image_name0 = str(name0, encoding='ascii').rstrip('\0')
    image_name1 = str(name1, encoding='ascii').rstrip('\0')

    texture_name0, texture_ext0 = os.path.splitext(image_name0)
    texture_name1, texture_ext1 = os.path.splitext(image_name1)

    texture = None

    if texture_name0 not in bpy.data.textures:
        texture = bpy.data.textures.new(texture_name0, 'IMAGE')

        texture_image = None

        if image_name0 not in bpy.data.images:
            fexts = [texture_ext0, '.dds', texture_ext0 + '.dds']

            fnames = [texture_name0]

            spaths = [os.path.dirname(elu.name), bpy.context.user_preferences.filepaths.texture_directory]

            fpaths = []

            for fname in fnames:
                for fext in fexts:
                    for spath in spaths:
                        fpath = os.path.join(os.path.normpath(spath), fname + fext)

                        if os.path.exists(fpath) is True:
                            fpaths.append(fpath)

            if len(fpaths) > 0:
                texture_image = bpy.data.images.load(fpaths[0])

            if texture_image is None:
                texture_image = bpy.data.images.new(fnames[0], 128, 128)
        else:
            texture_image = bpy.data.images[image_name0]

        if texture_image is not None:
            texture_image.mapping = 'UV'

            texture.image = texture_image
    else:
        texture = bpy.data.textures[texture_name0]

    return texture


def load_elu_material(elu, version):
    '''GunZ: The Duel'''
    index0, \
    index1 = struct.unpack('<2I', elu.read(8))

    ambient_color = struct.unpack('<4f', elu.read(16))
    diffuse_color = struct.unpack('<4f', elu.read(16))
    specular_color = struct.unpack('<4f', elu.read(16))
    specular_power = struct.unpack('<f', elu.read(4))[0]

    elu.seek(4, os.SEEK_CUR) # unknown: 1 unsigned long integer

    material_name = "z_material.{0:03}".format(index0)

    material = None
    
    if material_name not in bpy.data.materials:
        material = bpy.data.materials.new(material_name)

        material.diffuse_color = diffuse_color[:-1]
        material.alpha = diffuse_color[-1]
        material.specular_color = specular_color[:-1]
        material.specular_alpha = specular_color[-1]
        material.specular_intensity = specular_power

        material.use_shadeless = True
        material.use_mist = False
        material.use_raytrace = False
        material.use_face_texture = True
        material.use_face_texture_alpha = True
    else:
        material = bpy.data.materials[material_name]

    return material


def load_elu_textured_material(elu, version):
    '''GunZ: The Duel'''
    material = load_elu_material(elu, version)

    texture = load_elu_texture(elu, version)

    two_sided = 0

    if version > ELU_VERSIONS.x5001:
        two_sided = struct.unpack('<I', elu.read(4))[0]

    if version > ELU_VERSIONS.x5003:
        additive = struct.unpack('<I', elu.read(4))[0]

    alpha_percent = 0

    if version > ELU_VERSIONS.x5006:
        alpha_percent = struct.unpack('<I', elu.read(4))[0]

    if material is not None and \
       texture is not None:
        material_texture_slot = material.texture_slots.add()

        material_texture_slot.texture = texture

        material_texture_slot.texture_coords = 'UV'
        material_texture_slot.uv_layer = 'z_uv_texture'


def load_elu(elu, version):
    material_count, \
    mesh_count = struct.unpack('<2I', elu.read(8))

    if material_count > 0 and \
       version < ELU_VERSIONS.x5008:
        for i in range(material_count):
            load_elu_textured_material(elu, version)

    bip_mesh_objects = []

    z_mesh_objects = []

    names = [] # hack for GunZ: The Second Duel and RaiderZ

    for i in range(mesh_count):
        mesh_object = load_elu_mesh(elu, version)

        if mesh_object is not None:
            names.append(mesh_object.name)

            parent_mesh_object = mesh_object.parent

            if mesh_object.type == 'MESH':
                if mesh_object.data.bip_settings.is_bip is True:
                    bip_mesh_objects.append(mesh_object)
                else:
                    z_mesh_objects.append(mesh_object)

    scene = bpy.context.scene

    if len(bip_mesh_objects) > 0:
        armature = bpy.data.armatures.new('Armature')

        armature.use_mirror_x = False

        armature_object = bpy.data.objects.new('Armature', armature)

        armature_object.select = True

        scene.objects.link(armature_object)

        scene.update()

        scene.objects.active = armature_object

        bpy.ops.object.mode_set(mode='EDIT')

        for bip_mesh_object in bip_mesh_objects:
            bip_mesh = bip_mesh_object.data

            bone_name = bip_mesh_object.name if version < ELU_VERSIONS.x500E else str(names.index(bip_mesh_object.name))

            edit_bone = armature.edit_bones.new(bone_name)

            #edit_bone.use_connected = True
            #edit_bone.use_inherit_rotation = False
            #edit_bone.use_inherit_scale = False
            #edit_bone.use_local_location = False

            world_matrix = bip_mesh_object.matrix_world.copy()

            world_translation = world_matrix.to_translation()

            edit_bone.head.x = world_translation[0]
            edit_bone.head.y = world_translation[1]
            edit_bone.head.z = world_translation[2]

            edit_bone.tail = edit_bone.head + mathutils.Vector((0.0, 0.5, 0.0))

            bip_sibling_count = 0

            if bip_mesh_object.parent is not None and \
               bip_mesh_object.parent.data.bip_settings.is_bip is True:
                parent_bone_name = bip_mesh_object.parent.name if version < ELU_VERSIONS.x500E else str(names.index(bip_mesh_object.parent.name))

                edit_parent_bone = armature.edit_bones[parent_bone_name]

                edit_bone.parent = edit_parent_bone

                bip_sibling_count = sum(int(bip_sibling_mesh_object.data.bip_settings.is_bip) for bip_sibling_mesh_object in bip_mesh_object.parent.children)

                if bip_sibling_count == 1:
                    edit_parent_bone.tail = edit_bone.head

        bpy.ops.object.mode_set(mode='OBJECT')

        for z_mesh_object in z_mesh_objects:
            armature_modifier = z_mesh_object.modifiers.new('z_armature', 'ARMATURE')

            armature_modifier.object = armature_object

            if z_mesh_object.parent is None:
                z_mesh_object.parent = armature_object

        scene.update()


def load_from_path(path, context=None):
    logging.basicConfig(level=logging.DEBUG)

    logging.info("Opening file: %s", path)

    with io.open(path, mode='r+b') as elu:
        magic, \
        version = struct.unpack('<2I', elu.read(8))

        if magic != ELU_MAGIC or \
           version not in ELU_VERSIONS:
            logging.error('File not supported')

            return {
                'CANCELLED'
            }

        logging.debug("Version: %x", version)

        load_elu(elu, version)

    return {
        'FINISHED'
    }
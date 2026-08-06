"""
gltf.py -- 极简 glb (glTF Binary) 加载器

从外部 AI 生成的 .glb 中提取静态网格 (POSITION + NORMAL + indices)，
供自研引擎以 InstancedMesh 渲染。只支持单 mesh 的静态模型
(three.ws / 腾讯混元 等生成器输出的 LowPoly 模型通常满足此要求)。

输出统一为 (verts: float32[N,6] (pos3+normal3), indices: uint32[M])，
并做归一化: 脚底对齐 y=0, 总高缩放到 target_height。
"""
from __future__ import annotations

import json
import math
import os
import struct

import numpy as np

F32 = np.float32
U32 = np.uint32

_COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
              5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_TYPE_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
           "MAT2": 4, "MAT3": 9, "MAT4": 16}


def load_glb(path, target_height=1.8, face_forward="+z"):
    """读取 glb, 返回 (verts[N,6], indices[M])。

    face_forward: 模型正面朝向的轴 ("+z" 原样 / "-z" 翻转 / "+x" 旋转),
                  three.ws 生成的模型通常正面朝 +Z, 引擎角色默认朝 -Z,
                  故默认不旋转 (朝 +Z), 由实体朝向系统统一处理。
    """
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"glTF":
        raise ValueError("not a glb file")
    # chunks: JSON + BIN
    off = 12
    js = None
    bin_data = b""
    while off < len(data):
        (length, ctype) = struct.unpack_from("<II", data, off)
        off += 8
        chunk = data[off:off + length]
        off += length
        if ctype == 0x4E4F534A:      # 'JSON'
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:    # 'BIN\0'
            bin_data = chunk
    if js is None:
        raise ValueError("no JSON chunk")

    mesh = js["meshes"][0]
    prim = mesh["primitives"][0]
    attrs = prim["attributes"]

    def accessor(aid):
        a = js["accessors"][aid]
        bv = js["bufferViews"][a.get("bufferView")]
        buf = js["buffers"][bv.get("buffer")]
        base = bv.get("byteOffset", 0) + (buf.get("byteOffset", 0) if bv.get("buffer") else 0)
        src = bin_data if bv.get("buffer") == 0 else b""
        comp = _COMPONENT[a["componentType"]]
        n = a["count"]
        cn = _TYPE_N[a["type"]]
        offv = a.get("byteOffset", 0) + base
        return np.frombuffer(src, comp, count=n * cn, offset=offv).reshape(n, cn).astype(F32)

    pos = accessor(attrs["POSITION"])
    nrm = accessor(attrs.get("NORMAL")) if "NORMAL" in attrs else \
        np.zeros_like(pos)
    idx = accessor(prim.get("indices")) if prim.get("indices") is not None \
        else np.arange(len(pos), dtype=F32)

    verts = np.concatenate([pos, nrm], axis=1).astype(F32)

    # 归一化: 脚底到 y=0, 总高 -> target_height
    lo = verts[:, 1].min()
    hi = verts[:, 1].max()
    h = max(hi - lo, 1e-6)
    s = target_height / h
    verts[:, 0:3] *= s
    verts[:, 0] -= verts[:, 0].mean()
    verts[:, 1] -= lo * s
    verts[:, 2] -= verts[:, 2].mean()

    # 法线随缩放归一
    n = verts[:, 3:6]
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-6)

    return verts.astype(F32), idx.astype(U32)


def load_or_none(path, target_height=1.8):
    """加载失败返回 None (调用方回退到程序化模型)。"""
    try:
        return load_glb(path, target_height)
    except Exception as ex:  # noqa: BLE001
        print(f"[gltf] load fail {path}: {ex}")
        return None

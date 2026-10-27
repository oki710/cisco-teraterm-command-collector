"""Tiny ctypes harness for real Oniguruma regex checks, not a TTL emulator.

Uses UTF-8, Ruby syntax and no flags, the defaults in upstream ttmdde.c.
Local libonig version is reported; this does not exercise Tera Term's streaming
buffer or GUI. The test samples and patterns are supplied by the caller.
"""
from __future__ import annotations
import ctypes as C
import ctypes.util


class ErrorInfo(C.Structure):
    _fields_ = [('enc', C.c_void_p), ('par', C.c_void_p), ('par_end', C.c_void_p)]


class Region(C.Structure):
    _fields_ = [('allocated', C.c_int), ('num_regs', C.c_int),
                ('beg', C.POINTER(C.c_int)), ('end', C.POINTER(C.c_int)),
                ('history_root', C.c_void_p)]


class Onig:
    def __init__(self):
        name = ctypes.util.find_library('onig')
        if not name:
            raise RuntimeError('libonig is unavailable; do not substitute another regex engine silently')
        self.lib = C.CDLL(name)
        self.lib.onig_new.argtypes = [C.POINTER(C.c_void_p), C.c_void_p, C.c_void_p,
                                     C.c_uint, C.c_void_p, C.c_void_p, C.POINTER(ErrorInfo)]
        self.lib.onig_new.restype = C.c_int
        self.lib.onig_search.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p,
                                        C.c_void_p, C.c_void_p, C.POINTER(Region), C.c_uint]
        self.lib.onig_search.restype = C.c_int
        self.lib.onig_region_new.restype = C.POINTER(Region)
        self.lib.onig_region_free.argtypes = [C.POINTER(Region), C.c_int]
        self.lib.onig_free.argtypes = [C.c_void_p]
        self.lib.onig_version.restype = C.c_char_p
        self.encoding = C.addressof(C.c_char.in_dll(self.lib, 'OnigEncodingUTF8'))
        self.syntax = C.addressof(C.c_char.in_dll(self.lib, 'OnigSyntaxRuby'))
        self.version = self.lib.onig_version().decode()

    def search(self, pattern: str, text: str):
        raw_pattern = pattern.encode('utf-8')
        raw_text = text.encode('utf-8')
        p = C.create_string_buffer(raw_pattern)
        t = C.create_string_buffer(raw_text)
        reg = C.c_void_p()
        err = ErrorInfo()
        rc = self.lib.onig_new(C.byref(reg), C.addressof(p), C.addressof(p) + len(raw_pattern),
                               0, self.encoding, self.syntax, C.byref(err))
        if rc:
            msg = C.create_string_buffer(256)
            self.lib.onig_error_code_to_str(msg, rc, C.byref(err))
            raise ValueError(f'Oniguruma compile error {rc}: {msg.value.decode()}: {pattern!r}')
        region = self.lib.onig_region_new()
        try:
            start, end = C.addressof(t), C.addressof(t) + len(raw_text)
            rc = self.lib.onig_search(reg, start, end, start, end, region, 0)
            if rc == -1:
                return None
            if rc < -1:
                raise ValueError(f'Oniguruma search error {rc}')
            v = region.contents
            groups = [None if v.beg[i] < 0 else raw_text[v.beg[i]:v.end[i]].decode('utf-8')
                      for i in range(v.num_regs)]
            return {'start': rc, 'end': v.end[0], 'groups': groups}
        finally:
            self.lib.onig_region_free(region, 1)
            self.lib.onig_free(reg)


if __name__ == '__main__':
    o = Onig()
    assert o.search(r'^sw[0-9]+#$','sw1#')['groups'][0] == 'sw1#'
    assert o.search(r'^sw[0-9]+#$','sw1# show ver') is None
    assert o.search(r'\Asw1#\z','sw1#')['groups'][0] == 'sw1#'
    print('Oniguruma', o.version, 'smoke checks passed')
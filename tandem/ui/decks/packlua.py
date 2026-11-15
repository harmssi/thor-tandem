"""Lua 5.4 for companion packs, through ctypes on the system's liblua (no lua program, no pip package needed).

One Lua state per pack, used from one thread only. The pack's script never calls back into Python with anything but
plain values, and Python never raises through Lua: a C function written in Python cannot call lua_error (the longjmp would
cross Python's own stack frames). So everything that can fail is wrapped on the Lua side (BOOT below): the functions
Python provides return nil plus a reason, and the Lua wrappers turn that into a Lua error. Limits are a count hook written
in Lua (instructions, CPU time, memory), set before the sandbox takes `debug` away.
"""
import ctypes
from ctypes import POINTER, c_char_p, c_double, c_int, c_longlong, c_size_t, c_ssize_t, c_void_p

NAMES = ('liblua-5.4.so', 'liblua5.4.so.0', 'liblua.so.5.4', 'liblua5.4.so', 'liblua.5.4.dylib', 'liblua5.4.dylib', 'liblua.dylib')
CFUNC = ctypes.CFUNCTYPE(c_int, c_void_p)
_lib = None

# The sandbox and the pack API (see gba-duo-wide/docs-packs and app/src/main/cpp/script.c). Arguments: the functions
# from Python. Returns the function Python drives the pack with.
BOOT = r'''
local rd, read, gfxraw, lzraw, lograw, src, bankraw = ...
local sethook, clock, count = debug.sethook, os.clock, collectgarbage
local error, pcall, load, type, next, tostring, rawlen = error, pcall, load, type, next, tostring, rawlen
local fmt, gsub, byte, concat, unpack = string.format, string.gsub, string.byte, table.concat, table.unpack
local mtype, toint = math.type, math.tointeger
local left, deadline, why = 0, 0, nil
local STOP = {}  -- raised when a limit is hit; the pack's own pcall hands it on (below), so nothing can swallow it

local function stop(reason)
  why = why or reason
  error(STOP, 0)
end
local function hook()
  left = left - 1000
  if left <= 0 then stop("script exceeded its instruction budget") end
  if clock() > deadline then stop("script exceeded its time limit") end
  if count("count") > 16384 then
    count("collect")  -- garbage does not count
    if count("count") > 16384 then stop("script exceeded its 16 MB of memory") end
  end
end
sethook(hook, "", 1000)

local function charge(n)
  left = left - n
  if left <= 0 then stop("script exceeded its instruction budget") end
end
local function passed(ok, ...)
  if not ok and ... == STOP then error(STOP, 0) end
  return ok, ...
end
local rawpcall, rawxpcall = pcall, xpcall
_G.pcall = function(f, ...) return passed(rawpcall(f, ...)) end
_G.xpcall = function(f, handler, ...)
  return passed(rawxpcall(f, function(e) if e == STOP then return STOP end return handler(e) end, ...))
end
local function int(v)
  local i = toint(v)
  if not i then error("integer expected, got " .. type(v), 3) end
  return i
end
local function r(a, n)
  local v = rd(int(a), n)
  if not v then error("the emulator is not answering", 3) end
  return v
end

local esc = { ['"'] = '\\"', ['\\'] = '\\\\', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
local function quote(s) return '"' .. gsub(s, '[%c"\\]', function(c) return esc[c] or fmt("\\u%04x", byte(c)) end) .. '"' end
local function encode(v, depth, out)
  local t = type(v)
  if t == "string" then out[#out + 1] = quote(v)
  elseif t == "number" then
    if mtype(v) == "integer" then out[#out + 1] = fmt("%d", v)
    elseif v ~= v or v == 1 / 0 or v == -1 / 0 then out[#out + 1] = "null"
    else out[#out + 1] = fmt("%.17g", v) end
  elseif t == "boolean" then out[#out + 1] = v and "true" or "false"
  elseif t == "table" and depth <= 32 then
    local n, c = rawlen(v), 0
    for _ in next, v do c = c + 1 end
    if n > 0 and c == n then  -- a list: 1..n and nothing else
      out[#out + 1] = "["
      for i = 1, n do
        if i > 1 then out[#out + 1] = "," end
        encode(v[i], depth + 1, out)
      end
      out[#out + 1] = "]"
    else
      out[#out + 1] = "{"
      local first = true
      for k, x in next, v do
        if type(k) == "string" then
          if not first then out[#out + 1] = "," end
          first = false
          out[#out + 1] = quote(k)
          out[#out + 1] = ":"
          encode(x, depth + 1, out)
        end
      end
      out[#out + 1] = "}"
    end
  else out[#out + 1] = "null" end
end
local function json(v)
  left = 20000000  -- writing the answer down is not the pack's work
  local out = {}
  encode(v, 0, out)
  return concat(out)
end

local function signed(n, bits) return function(a) local v = r(a, n); return v >= bits // 2 and v - bits or v end end
local function refused() return false, "Tandem only reads the game's memory" end
mem = {
  u8 = function(a) return r(a, 1) end, u16 = function(a) return r(a, 2) end, u32 = function(a) return r(a, 4) end,
  s8 = signed(1, 0x100), s16 = signed(2, 0x10000), s32 = signed(4, 0x100000000),
  read = function(a, n)
    n = int(n)
    if n < 0 then n = 0 elseif n > 65536 then n = 65536 end
    charge(n)
    local s = read(int(a), n)
    if not s then error("the emulator is not answering", 2) end
    return s
  end,
  write8 = refused, write16 = refused, write32 = refused, write = refused,
}
if bankraw then
  mem.bank8 = function(bank, a)
    bank = int(bank)
    if bank < 0 or bank > 255 then error("mem.bank8: bank out of range", 2) end
    local v = bankraw(bank, int(a))
    if not v then error("the emulator is not answering", 2) end
    return v
  end
end

local function picture(kind)
  return function(t)
    if type(t) ~= "table" then error("gfx." .. kind .. ": a table is expected", 2) end
    local key, why = gfxraw(kind, json(t))
    if not key then error("gfx." .. kind .. ": " .. tostring(why), 2) end
    return key
  end
end
gfx = { decode = picture("decode"), tilemap = picture("tilemap"), sprite = picture("sprite"), layers = picture("layers") }
lz77 = function(a)
  local s, why = lzraw(int(a))
  if not s then error("lz77: " .. tostring(why), 2) end
  charge(#s)
  return s
end
log = function(v) lograw(tostring(v)) end

local modules = {}
pack = { require = function(name)
  if type(name) ~= "string" or name == "" or name:find("..", 1, true) or name:find("[^%w_%-%.]") then
    error("pack.require: invalid module name '" .. tostring(name) .. "'", 2)
  end
  local hit = modules[name]
  if hit ~= nil then return hit end
  local text = src(name)
  if not text then error("pack.require: no such module '" .. name .. "'", 2) end
  local chunk, why = load(text, "=" .. name, "t")
  if not chunk then error(why, 0) end
  local result = chunk()
  modules[name] = result
  return result
end }

for _, name in next, { "dofile", "loadfile", "load", "collectgarbage", "require", "print", "io", "os", "package", "debug", "coroutine" } do _G[name] = nil end
string.dump = nil

local function result(ok, value, ...)
  if not ok and value == STOP then return false, why end
  return ok, value, ...
end
local function run(budget, secs, f, ...)
  left, deadline, why = budget, clock() + secs, nil
  return result(rawpcall(f, ...))
end
local function answer(ok, value)
  if not ok then return false, tostring(value) end
  local fine, text = result(rawpcall(json, value))
  if not fine then return false, tostring(text) end
  return true, text
end

return function(op, a, b)
  if op == "load" then  -- a: the script, b: its name. The top level and init(): 5M instructions.
    local chunk, why = load(a, b, "t")
    if not chunk then return false, why end
    local ok, e = run(5000000, 10, function()
      chunk()
      if type(init) == "function" then init() end
    end)
    if not ok then return false, tostring(e) end
    return true, ""
  elseif op == "update" then  -- a: the UI state as a Lua table
    local state = load("return " .. a, "=ui", "t")()
    ui = state
    if type(update) ~= "function" then return true, "{}" end
    local ok, value = run(1000000, 5, update, state)
    if ok and type(value) ~= "table" then return false, "update() must return a table" end
    return answer(ok, value)
  elseif op == "action" then  -- a: its name, b: the arguments as a Lua table with n
    local f = type(actions) == "table" and actions[a]
    if type(f) ~= "function" then return false, "no action '" .. tostring(a) .. "'" end
    local args = load("return " .. b, "=args", "t")()
    local ok, value = run(1000000, 5, f, unpack(args, 1, args.n))
    if ok and type(value) ~= "table" then return true, "null" end
    return answer(ok, value)
  end
  return false, "unknown call"
end
'''


def lib():
    """liblua 5.4 with every function's types declared (a wrong default int would cut pointers in half)."""
    global _lib
    if _lib is not None: return _lib
    found = None
    for name in NAMES:
        try: found = ctypes.CDLL(name); break
        except OSError: continue
    if found is None: raise OSError('Lua 5.4 fehlt (liblua-5.4.so)')
    P, I, LL, D, S = c_void_p, c_int, c_longlong, c_double, c_size_t
    for name, res, args in (
            ('luaL_newstate', P, []), ('luaL_openlibs', None, [P]), ('lua_close', None, [P]), ('lua_version', D, [P]),
            ('luaL_loadbufferx', I, [P, c_char_p, S, c_char_p, c_char_p]), ('lua_pcallk', I, [P, I, I, I, c_ssize_t, P]),
            ('lua_settop', None, [P, I]), ('lua_gettop', I, [P]), ('lua_type', I, [P, I]), ('lua_isinteger', I, [P, I]),
            ('lua_tointegerx', LL, [P, I, P]), ('lua_tonumberx', D, [P, I, P]), ('lua_toboolean', I, [P, I]),
            ('lua_tolstring', P, [P, I, POINTER(S)]), ('lua_pushnil', None, [P]), ('lua_pushinteger', None, [P, LL]),
            ('lua_pushnumber', None, [P, D]), ('lua_pushboolean', None, [P, I]), ('lua_pushlstring', P, [P, c_char_p, S]),
            ('lua_pushcclosure', None, [P, CFUNC, I]), ('lua_pushvalue', None, [P, I]), ('lua_checkstack', I, [P, I])):
        fn = getattr(found, name)
        fn.restype, fn.argtypes = res, args
    _lib = found
    return found


def literal(value):
    """A Python value as Lua source: the UI state and an action's arguments travel as text."""
    if value is None: return 'nil'
    if value is True: return 'true'
    if value is False: return 'false'
    if isinstance(value, int): return str(value) if -2 ** 63 <= value < 2 ** 63 else 'nil'
    if isinstance(value, float): return repr(value) if value == value and abs(value) != float('inf') else 'nil'
    if isinstance(value, str):
        out = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\0', '\\0')
        return '"' + out + '"'
    if isinstance(value, dict): return '{' + ','.join(f'[{literal(str(k))}]={literal(v)}' for k, v in value.items()) + '}'
    if isinstance(value, (list, tuple)): return '{' + ''.join(literal(v) + ',' for v in value) + f'n={len(value)}' + '}'
    return 'nil'


class Lua:
    """A sandboxed Lua state. `api` are the Python functions behind mem/gfx/log/pack.require (plain values in and out)."""

    def __init__(self, rd, read, gfx, lz, log, src, bank=None):
        self.lib = L = lib()
        self.L = L.luaL_newstate()
        if not self.L: raise MemoryError('Lua: kein Speicher')
        if L.lua_version(self.L) != 504: raise OSError('liblua ist nicht Version 5.4')
        L.luaL_openlibs(self.L)
        self.keep = [self.wrap(fn) for fn in (rd, read, gfx, lz, log, src)] + ([self.wrap(bank)] if bank else [])
        code = BOOT.encode()
        if L.luaL_loadbufferx(self.L, code, len(code), b'=tandem', b't'): raise RuntimeError(self.text(-1))
        for fn in self.keep: L.lua_pushcclosure(self.L, fn, 0)
        if L.lua_pcallk(self.L, len(self.keep), 1, 0, 0, None): raise RuntimeError(self.text(-1))  # the driver stays at index 1

    def text(self, index):
        size = c_size_t()
        at = self.lib.lua_tolstring(self.L, index, ctypes.byref(size))
        return ctypes.string_at(at, size.value).decode('utf-8', 'replace') if at else ''

    def wrap(self, fn):
        L_ = self.lib
        def call(L):
            try:
                args = []
                for i in range(1, L_.lua_gettop(L) + 1):
                    kind = L_.lua_type(L, i)
                    if kind == 3: args.append(L_.lua_tointegerx(L, i, None) if L_.lua_isinteger(L, i) else L_.lua_tonumberx(L, i, None))
                    elif kind == 4:
                        size = c_size_t()
                        args.append(ctypes.string_at(L_.lua_tolstring(L, i, ctypes.byref(size)), size.value))
                    elif kind == 1: args.append(bool(L_.lua_toboolean(L, i)))
                    else: args.append(None)
                out = fn(*args)
            except Exception as error:  # nothing may leave through the C frames: Lua gets nil and the reason
                out = (None, f'{error}' or type(error).__name__)
            try:
                for v in out if isinstance(out, tuple) else (out,):
                    if v is None: L_.lua_pushnil(L)
                    elif isinstance(v, bool): L_.lua_pushboolean(L, v)
                    elif isinstance(v, int): L_.lua_pushinteger(L, v)
                    elif isinstance(v, float): L_.lua_pushnumber(L, v)
                    else:
                        data = v.encode() if isinstance(v, str) else bytes(v)
                        L_.lua_pushlstring(L, data, len(data))
                return len(out) if isinstance(out, tuple) else 1
            except Exception: return 0
        return CFUNC(call)

    def call(self, op, a='', b=''):
        """-> (ok, text): the JSON the pack answered, or why it failed. Never raises for a script's mistake."""
        L, S = self.lib, self.L
        L.lua_settop(S, 1)
        L.lua_pushvalue(S, 1)
        for v in (op, a, b):
            data = v.encode() if isinstance(v, str) else v
            L.lua_pushlstring(S, data, len(data))
        if L.lua_pcallk(S, 3, 2, 0, 0, None): return False, self.text(-1)
        return bool(L.lua_toboolean(S, 2)), self.text(3)

    def close(self):
        if self.L: self.lib.lua_close(self.L)
        self.L, self.keep = None, []

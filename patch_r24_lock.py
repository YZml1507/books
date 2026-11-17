# -*- coding: utf-8 -*-
import io, sys
JS="/opt/books/app/web/static/app.js"
with io.open(JS,"r",encoding="utf-8") as f: a=f.read()
def rep(tag,old,new,n=1):
    global a
    if a.count(old)!=n: sys.exit("FAIL[%s]: count=%d"%(tag,a.count(old)))
    if new in a: sys.exit("FAIL[%s]: 已打过"%tag)
    a=a.replace(old,new,n)

OLD = """  function _phPinHash(pin) {
    return crypto.subtle.digest('SHA-256',
      new TextEncoder().encode('books-histlock:' + pin))
      .then(function (buf) {
        return 'v1:' + Array.prototype.map.call(new Uint8Array(buf),
          function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
      });
  }"""
NEW = """  /* R24（用户实测：「点了加锁→输密码→点锁定，它说要 HTTPS」）：
   * crypto.subtle 只在安全上下文（https 或 localhost）里存在，纯 http 下
   * 是 undefined，旧实现一进函数就 throw，锁整个瘫掉。改用同口径纯 JS
   * SHA-256——输出与 crypto.subtle 逐位一致，设过锁的老用户哈希照样
   * 对得上，不用「忘掉我的数据」重设。 */
  function _sha256hex(ascii) {
    var _K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,
      0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,
      0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,
      0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,
      0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,
      0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,
      0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,
      0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,
      0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,
      0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,
      0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    var _H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,
      0x9b05688c,0x1f83d9ab,0x5be0cd19];
    function _rr(x, n) { return (x >>> n) | (x << (32 - n)); }
    var _b = [], i, j;
    for (i = 0; i < ascii.length; i++) _b.push(ascii.charCodeAt(i) & 0xff);
    var _len = _b.length;
    _b.push(0x80);
    while (_b.length % 64 !== 56) _b.push(0);
    var _bits = _len * 8;
    for (j = 7; j >= 0; j--) _b.push(Math.floor(_bits / Math.pow(256, j)) % 256);
    var _w = new Array(64), _a, _bb, _c, _d, _e, _f, _g, _h, _t1, _t2;
    for (i = 0; i < _b.length; i += 64) {
      for (j = 0; j < 16; j++) {
        _w[j] = (_b[i + j * 4] << 24) | (_b[i + j * 4 + 1] << 16) |
                (_b[i + j * 4 + 2] << 8) | (_b[i + j * 4 + 3]);
      }
      for (j = 16; j < 64; j++) {
        var _s0 = _rr(_w[j - 15], 7) ^ _rr(_w[j - 15], 18) ^ (_w[j - 15] >>> 3);
        var _s1 = _rr(_w[j - 2], 17) ^ _rr(_w[j - 2], 19) ^ (_w[j - 2] >>> 10);
        _w[j] = (_w[j - 16] + _s0 + _w[j - 7] + _s1) | 0;
      }
      _a = _H[0]; _bb = _H[1]; _c = _H[2]; _d = _H[3];
      _e = _H[4]; _f = _H[5]; _g = _H[6]; _h = _H[7];
      for (j = 0; j < 64; j++) {
        var _S1 = _rr(_e, 6) ^ _rr(_e, 11) ^ _rr(_e, 25);
        var _ch = (_e & _f) ^ (~_e & _g);
        _t1 = (_h + _S1 + _ch + _K[j] + _w[j]) | 0;
        var _S0 = _rr(_a, 2) ^ _rr(_a, 13) ^ _rr(_a, 22);
        var _mj = (_a & _bb) ^ (_a & _c) ^ (_bb & _c);
        _t2 = (_S0 + _mj) | 0;
        _h = _g; _g = _f; _f = _e; _e = (_d + _t1) | 0;
        _d = _c; _c = _bb; _bb = _a; _a = (_t1 + _t2) | 0;
      }
      _H[0] = (_H[0] + _a) | 0; _H[1] = (_H[1] + _bb) | 0;
      _H[2] = (_H[2] + _c) | 0; _H[3] = (_H[3] + _d) | 0;
      _H[4] = (_H[4] + _e) | 0; _H[5] = (_H[5] + _f) | 0;
      _H[6] = (_H[6] + _g) | 0; _H[7] = (_H[7] + _h) | 0;
    }
    var _out = '';
    for (i = 0; i < 8; i++) {
      var _x = _H[i] >>> 0;
      for (j = 3; j >= 0; j--) {
        _out += ('0' + ((_x >>> (j * 8)) & 0xff).toString(16)).slice(-2);
      }
    }
    return _out;
  }
  function _phPinHash(pin) {
    /* 保留 Promise 外形——调用方是 .then() 链，不改调用点 */
    try {
      return Promise.resolve('v1:' + _sha256hex('books-histlock:' + pin));
    } catch (e) { return Promise.reject(e); }
  }"""
rep("lock-sha", OLD, NEW)
with io.open(JS,"w",encoding="utf-8") as f: f.write(a)
print("R24 lock OK")

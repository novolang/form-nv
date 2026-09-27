#!/usr/bin/env python3
"""Read the emitted LLVM for form-nv's allocation probe and say whether
any function in `formscan` can put a cell on the heap.

Run by tests/alloc_scan.sh three times: once on the package as it
stands, and twice on copies with an allocation spliced into the scanner.
Those two copies are what the scan and the compiler respectively have to
catch, because a check that cannot fail is not a check.

The IR is emitted at `--opt=0`, so every function of the module is still
a function to attribute an allocation to.
"""
import re
import sys

# Every way a function can put a cell on the heap: a runtime entry point
# with `alloc` in its name, and the four that allocate inside the
# runtime on the caller's behalf.
ALLOCATOR = re.compile(r'call [^\n]*@(novo_\w*alloc\w*)\(')
BOXERS = ['novo_some_int', 'novo_some_float',
          'novo_str_byte_at(', 'novo_bytes_byte_at(']

CORE = re.compile(r'^novo_user_formscan_')

FNS = re.compile(r'^define[^\n]*?@([A-Za-z0-9_.]+)\([^\n]*\{\n(.*?)\n\}',
                 re.S | re.M)

# The module has twenty-three `pub fn`s and the probe reaches every one.
# Fewer than this in the IR means the probe or the name scheme moved.
FLOOR = 23


def main(path):
    src = open(path).read()
    seen, offenders = 0, []
    for m in FNS.finditer(src):
        name, body = m.group(1), m.group(2)
        if not CORE.match(name):
            continue
        seen += 1
        for m2 in ALLOCATOR.finditer(body):
            offenders.append('%s: %s' % (name, m2.group(1)))
        for boxer in BOXERS:
            if 'call' in body and ('@' + boxer) in body:
                offenders.append('%s: %s' % (name, boxer.rstrip('(')))
    if seen < FLOOR:
        print('FAIL only %d formscan function(s) in the IR, expected at least '
              '%d — the probe or the name scheme moved, and this check was '
              'measuring nothing' % (seen, FLOOR))
    elif offenders:
        print('FAIL ' + '; '.join(sorted(set(offenders))))
    else:
        print('OK %d function(s) in formscan, zero heap cells' % seen)


if __name__ == '__main__':
    main(sys.argv[1])

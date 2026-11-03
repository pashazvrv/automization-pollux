import sys; sys.path.insert(0, __file__.rsplit('/',1)[0])
from lib import show
lo, hi = int(sys.argv[1]), int(sys.argv[2])
show(lo, hi, *(int(x) for x in sys.argv[3:]))

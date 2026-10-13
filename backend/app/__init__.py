from . import nailsystem_runtime
from .config import load_env

load_env()  # development only: .env fills in what the environment lacks (ignored in product mode)
# Everything else comes from here: in product mode the installed layout, salon.json and the protected secrets store.
# Must run before any submodule reads os.environ.
RUNTIME = nailsystem_runtime.bootstrap("checkin")

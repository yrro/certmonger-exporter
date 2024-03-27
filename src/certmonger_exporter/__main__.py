import faulthandler
import signal
import sys

from certmonger_exporter import * 

faulthandler.enable()
faulthandler.register(signal.SIGUSR1, all_threads=True)
configure_logging()
sys.excepthook = excepthook
sys.exit(main(sys.argv))

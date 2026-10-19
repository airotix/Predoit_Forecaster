"""Background workflow: secrets are read from server environment, never argv."""
import sys
from automatic_forecast import execute
from database import get_connection

if __name__=='__main__':execute(sys.argv[1],get_connection)

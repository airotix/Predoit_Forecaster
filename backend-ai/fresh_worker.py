"""Independent export worker; credentials arrive only via stdin, never argv or disk."""
import json
import sys
from fresh_joolan import run_export

if __name__=='__main__':
    key=json.loads(sys.stdin.readline())['apiKey']
    run_export(sys.argv[1],key)

import subprocess
import sys
import os

def main():
    gateway = os.path.join(os.path.dirname(__file__), '..', 'gateway.py')
    subprocess.run([sys.executable, gateway])
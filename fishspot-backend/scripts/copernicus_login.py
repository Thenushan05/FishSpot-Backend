"""
Secure Copernicus Marine login helper.
Reads credentials from environment variables:
  COPERNICUS_USERNAME
  COPERNICUS_PASSWORD

Usage (PowerShell):
  $env:COPERNICUS_USERNAME='user@example.com'; $env:COPERNICUS_PASSWORD='secret'; python scripts/copernicus_login.py

The script will NOT print the password. It will call copernicusmarine.login() to store credentials as the package does.
"""
import os
import sys

try:
    import copernicusmarine
except Exception as e:
    print('ERROR: copernicusmarine not installed in this environment:', e)
    sys.exit(1)

username = os.environ.get('COPERNICUS_USERNAME')
password = os.environ.get('COPERNICUS_PASSWORD')

if not username or not password:
    print('Missing environment variables COPERNICUS_USERNAME and/or COPERNICUS_PASSWORD')
    print('Set them in your shell prior to running this script. Example (PowerShell):')
    print("$env:COPERNICUS_USERNAME='you@example.com'; $env:COPERNICUS_PASSWORD='YourSecret'")
    sys.exit(1)

# Perform login
try:
    copernicusmarine.login(username=username, password=password)
    print('✅ Logged in and credentials saved by copernicusmarine')
except Exception as e:
    print('Login failed:', e)
    sys.exit(2)

import os
import sys
import subprocess
import time
import requests
import signal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_port_in_use(port):
    """Check if port is in use"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def start_django_server():
    """Start Django test server"""
    port = 8002
    
    # Check if port is already in use
    if is_port_in_use(port):
        logger.error(f"Port {port} is already in use!")
        return None
        
    # Start Django server
    server = subprocess.Popen(
        [sys.executable, 'manage.py', 'runserver', f'{port}'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    for _ in range(30):  # Wait up to 30 seconds
        try:
            response = requests.get(f'http://localhost:{port}/admin/')
            if response.status_code == 200 or response.status_code == 302:
                logger.info(f"Django server started on port {port}")
                return server
        except requests.exceptions.ConnectionError:
            time.sleep(1)
            continue
            
    logger.error("Failed to start Django server!")
    return None

def run_tests():
    """Run the test suite"""
    try:
        result = subprocess.run(
            [sys.executable, 'tests/test_firebase_auth.py'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error running tests: {str(e)}")
        return False

def main():
    # Start Django server
    logger.info("Starting Django server...")
    server_process = start_django_server()
    
    if not server_process:
        logger.error("Failed to start server. Exiting...")
        return
        
    try:
        # Wait for server to be fully ready
        time.sleep(5)
        
        # Run tests
        logger.info("\nRunning tests...")
        success = run_tests()
        
        if success:
            logger.info("\n🎉 All tests completed successfully!")
        else:
            logger.error("\n❌ Some tests failed!")
            
    finally:
        # Clean up
        logger.info("\nStopping Django server...")
        os.kill(server_process.pid, signal.SIGTERM)
        server_process.wait()

if __name__ == '__main__':
    main()
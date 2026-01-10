import sys
import time
from pymilvus import MilvusClient, connections, utility

def test_connect(uri):
    print(f"Testing connection to {uri}...")
    try:
        # Try raw connection first
        if uri.startswith("http"):
             # MilvusClient wrapper
            client = MilvusClient(uri=uri, token="")
            print(f"✅ MilvusClient connected successfully to {uri}")
        else:
            # Lower level connection
            addr = uri.split(":") 
            host = addr[0]
            port = addr[1]
            connections.connect(alias="default", host=host, port=port)
            print(f"✅ connections.connect succeeded for {host}:{port}")
            print(f"Server Version: {utility.get_server_version()}")
    except Exception as e:
        print(f"❌ Failed to connect to {uri}: {e}")

if __name__ == "__main__":
    print("Python executable:", sys.executable)
    # Test 1: localhost (MilvusClient)
    test_connect("http://localhost:19530")
    
    # Test 2: 127.0.0.1 (MilvusClient)
    test_connect("http://127.0.0.1:19530")
    
    # Test 3: Legacy connection style
    test_connect("localhost:19530")

# Created by Eyal Asulin™ - [PEP8]
import socket
import keyboard
import cv2
import threading
import time
import sys


def send_command(command_socket, command_addr, command, debug=True, retry=3, timeout=5):
    """
    Send command to Tello and get response with timeout and retry mechanisms
    """
    if debug:
        print(f"   Sending command: {command}")
    
    # Set socket timeout for receiving response
    command_socket.settimeout(timeout)
    
    for attempt in range(retry):
        try:
            # Send the command
            if isinstance(command, str):
                command_socket.sendto(command.encode(), command_addr)
            else:
                command_socket.sendto(command, command_addr)
            
            # Wait for response
            try:
                response, ip = command_socket.recvfrom(1024)
                response = response.decode().strip()
                if debug:
                    print(f"   Response: {response}")
                return response
            except socket.timeout:
                if debug:
                    print(f"   Timeout waiting for response (attempt {attempt+1}/{retry})")
        except Exception as e:
            if debug:
                print(f"   Error sending command: {str(e)} (attempt {attempt+1}/{retry})")
        
        # Wait before retry
        if attempt < retry - 1:
            time.sleep(1)
    
    if debug:
        print(f"   Failed to get response after {retry} attempts for command: {command}")
    return None

def check_connection(command_socket, command_addr):
    """
    Verify connection to Tello drone
    """
    print("\n   Checking connection to Tello...")
    response = send_command(command_socket, command_addr, "command")
    
    if response == "ok":
        print("    Connection verified!")
        
        # Check battery level
        battery = send_command(command_socket, command_addr, "battery?")
        if battery and battery.isdigit():
            print(f"    Battery level: {battery}%")
            if int(battery) < 20:
                print("    Warning: Battery level low!")
        
        return True
    else:
        print("    Connection failed! Make sure you're connected to Tello's WiFi network.")
        print("   ℹ Tello WiFi name usually starts with 'TELLO-'")
        return False

def watch_video_stream(command_socket, command_addr):
    """
    Start and display video stream from Tello
    """    
    response = send_command(command_socket, command_addr, "streamon")
    if response != "ok":
        print("   Failed to start video stream. Response:", response)
        return False
        
    print("\n   Video streaming started!")
    print("   Connecting to video stream (this may take a few seconds)...")
    
    # Allow some time for streaming to initialize
    time.sleep(2)
    
    # Try to connect to the stream with multiple attempts
    cap = None
    for attempt in range(3):
        try:
            cap = cv2.VideoCapture('udp://192.168.10.1:11111')
            if cap.isOpened():
                print("    Connected to video stream!")
                break
            else:
                print(f"    Attempt {attempt+1}/3: Could not open video stream, retrying...")
                time.sleep(2)
        except Exception as e:
            print(f"    Video stream error: {str(e)}")
            time.sleep(2)
    
    if cap is None or not cap.isOpened():
        print("    Failed to connect to video stream after multiple attempts")
        send_command(command_socket, command_addr, "streamoff")
        return False
    
    # Count frames to detect video stream issues
    frame_count = 0
    start_time = time.time()
    
    try:
        while True:
            ret, frame = cap.read()
            if ret:
                frame_count += 1
                elapsed = time.time() - start_time
                
                # Display FPS every 30 frames
                if frame_count % 30 == 0:
                    fps = frame_count / elapsed
                    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                cv2.imshow('Tello Video Stream', frame)
                key = cv2.waitKey(1) & 0xFF
                if key == 27:  # 'Esc' key
                    break
            else:
                # If we can't read a frame, try to reconnect
                print("    Video frame lost, attempting to reconnect...")
                cap.release()
                cap = cv2.VideoCapture('udp://192.168.10.1:11111')
                if not cap.isOpened():
                    print("    Failed to reconnect to video stream")
                    break
    except Exception as e:
        print(f"    Error in video stream: {str(e)}")
    finally:
        if cap:
            cap.release()
        cv2.destroyAllWindows()
        send_command(command_socket, command_addr, "streamoff")
        print("   Video stream stopped")


def get_tello_status(command_socket, command_addr):
    """
    Get all available status information from Tello for debugging
    """
    print("\n    Requesting Tello status...")
    
    # Request status information
    response = send_command(command_socket, command_addr, "status?")
    if not response:
        print("    Failed to get status information")
        return
        
    # Parse and display information
    print("\n    Tello Status Information:")
    print("   " + "=" * 40)
    
    try:
        status_items = response.split(';')
        for item in status_items:
            if item:  # Skip empty items
                key, value = item.split(':') if ':' in item else (item, "N/A")
                print(f"   {key.strip()}: {value.strip()}")
    except Exception as e:
        print(f"    Error parsing status: {str(e)}")
        print(f"   Raw status: {response}")
    
    print("   " + "=" * 40)

def configure_wifi(command_socket, command_addr):
    """
    Configure Tello WiFi settings
    """
    print("\n    Configure WiFi Settings")
    print("    Warning: This will change the drone's WiFi settings and disconnect your current connection!")
    
    ssid = input("\n   Enter new wifi SSID: ")
    password = input("   Enter new wifi password: ")
    
    if not ssid or not password:
        print("    SSID and password cannot be empty!")
        return False
        
    command = "wifi " + ssid + " " + password
    response = send_command(command_socket, command_addr, command)
    
    if response == "ok":
        print("    WiFi settings changed successfully!")
        print("    The drone will disconnect and connect to the new network.")
        print(f"   ℹ New network: {ssid}")
        return True
    else:
        print("    Failed to change WiFi settings.")
        print("   Response:", response if response else "No response")
        return False


def establish_connection(max_attempts=3):
    """
    Establish and verify connection with the Tello drone
    """
    print("\n    Establishing connection with Tello drone...")
    
    for attempt in range(max_attempts):
        try:
            print(f"   Attempt {attempt+1}/{max_attempts} to connect")
            
            # Create socket
            command_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            command_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Set timeout for socket operations
            command_socket.settimeout(5)
            
            # Define address
            command_addr = ('192.168.10.1', 8889)
            
            # Bind socket
            try:
                command_socket.bind(('', 8889))
                print("    Socket binding successful")
            except socket.error as e:
                print(f"    Socket binding failed: {e}")
                print("    Port 8889 might be in use by another application")
                if attempt == max_attempts - 1:
                    return None
                time.sleep(2)
                continue
            
            # Enter SDK mode
            print("    Sending command to enter SDK mode...")
            command_socket.sendto(b"command", command_addr)
            
            try:
                response, _ = command_socket.recvfrom(1024)
                response = response.decode().strip()
                
                if response == "ok":
                    print("    Successfully entered SDK mode")
                    return command_socket, command_addr
                else:
                    print(f"    Unexpected response to SDK mode: {response}")
            except socket.timeout:
                print("    Timeout while waiting for SDK mode response")
                print("    Is the drone powered on? Are you connected to Tello WiFi?")
            except Exception as e:
                print(f"    Error during connection: {str(e)}")
            
            time.sleep(2)
        
        except Exception as e:
            print(f"    Connection error: {str(e)}")
            time.sleep(2)
    
    print("    Failed to establish connection after multiple attempts")
    print("   ℹ Troubleshooting tips:")
    print("     1. Make sure the drone is powered on")
    print("     2. Connect to the Tello WiFi network (usually starts with 'TELLO-')")
    print("     3. Check if any other application is using port 8889")
    print("     4. Try restarting the drone")
    return None

def main():
    print("""
    Tello Drone Controller 
   ============================""")
    
    print("    Connect to Tello WiFi network and press <<Shift>> to continue")
    print("    Waiting for connection...")
    
    while not keyboard.is_pressed("Shift"):
        pass
    
    print("    Starting connection process...")
    
    # Establish connection
    connection_result = establish_connection()
    if not connection_result:
        print("    Failed to establish connection")
        input("   Press Enter to exit...")
        return
    
    command_socket, command_addr = connection_result
    
    # Verify connection with battery check
    if not check_connection(command_socket, command_addr):
        print("    Connection verification failed")
        input("   Press Enter to exit...")
        return
    
    print("    Control has been successfully established!")
    
    # Create video thread but don't start automatically
    video_thread = threading.Thread(target=watch_video_stream, args=(command_socket, command_addr))
    video_thread.daemon = True
    video_started = False
      # Define video start function with closure to access video_started variable
    def start_video():
        nonlocal video_started
        if not video_started:
            video_thread.start()
            video_started = True
        else:
            print("    Video stream already started")
            
    # Define emergency stop function
    def emergency_stop():
        try:
            print("    EMERGENCY STOP ACTIVATED")
            # Send emergency command directly without waiting for response
            command_socket.sendto(b"emergency", command_addr)
            # Send multiple times to ensure it's received
            command_socket.sendto(b"emergency", command_addr)
            command_socket.sendto(b"emergency", command_addr)
            print("    Emergency stop command sent")
        except Exception as e:
            print(f"    Error sending emergency stop: {str(e)}")
    
    # Setup command handlers
    keyboard.on_press_key("1", lambda _: emergency_stop())
    keyboard.on_press_key("2", lambda _: start_video())
    keyboard.on_press_key("3", lambda _: send_command(command_socket, command_addr, "land"))
    keyboard.on_press_key("4", lambda _: configure_wifi(command_socket, command_addr))
    keyboard.on_press_key("6", lambda _: get_tello_status(command_socket, command_addr))
    keyboard.on_press_key("t", lambda _: send_command(command_socket, command_addr, "takeoff"))
      print("""
    CONTROLS:
    ===========
    1) Emergency - stop motors immediately
    2) Watch Video Stream
    3) Land
    4) Configure WiFi Password
    5) Exit
    6) Show Drone Status (Diagnostics)
    T) Take Off (Press T key)
    """)
    
    try:
        while not keyboard.is_pressed("5"):
            time.sleep(0.1)  # Reduce CPU usage
    except KeyboardInterrupt:
        print("\n   ℹ Program interrupted")
    finally:
        # Clean up
        print("\n    Shutting down...")
        try:
            # Try to land the drone if it might be flying
            send_command(command_socket, command_addr, "land", debug=False)
            time.sleep(1)
            # Turn off video stream if it was on
            send_command(command_socket, command_addr, "streamoff", debug=False)
        except:
            pass  # Ignore errors during shutdown
        
        print("    Exited safely")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n    Unexpected error: {str(e)}")
        print("   Detailed error information:")
        import traceback
        traceback.print_exc()
        input("\n   Press Enter to exit...")

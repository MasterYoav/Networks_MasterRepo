import socket
import argparse
from tkinter import Tk
from tkinter.filedialog import askopenfilename
from threading import Timer
# Predefined variables
DEFAULT_SERVER_HOST = "127.0.0.1"  # Default server host
DEFAULT_SERVER_PORT = 9999        # Default server port


"""
Reads a request file and extracts parameters into a dictionary.

:param file_path: Path to the .txt file
:return: A dictionary containing 'message', 'maximum_msg_size', 'window_size', and 'timeout'
"""
def parse_request_file(file_path: str) -> dict:

    params = {}
    try:
        with open(file_path, 'r') as file:
            for line in file:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip().strip('"')  # Remove whitespace and quotes
                    if key in ['maximum_msg_size', 'window_size', 'timeout']:
                        value = int(value)  # Convert numeric values to integers
                    params[key] = value

        # Validate required parameters
        required_keys = {'message', 'maximum_msg_size', 'window_size', 'timeout'}
        if not required_keys.issubset(params.keys()):
            missing_keys = required_keys - params.keys()
            raise ValueError(f"Missing required keys in file: {', '.join(missing_keys)}")

        return params
    except FileNotFoundError:
        print("Error: File not found.")
        raise
    except ValueError as ve:
        print(f"Error: {ve}")
        raise
    except Exception as e:
        print(f"Error reading or parsing file: {e}")
        raise


"""
Opens a file dialog for the user to select a file.
:return: The path of the selected file or None if no file is selected.
"""
def select_file():

    root = Tk()
    root.withdraw()  # Hide the main tkinter window
    root.attributes('-topmost', True)  # Bring the file dialog to the front
    file_path = askopenfilename(
        title="Select a .txt File",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )
    root.destroy()
    return file_path

class Client:

    def __init__(self, server_address: tuple[str, int], timeout: int, window_size: int):
        self.server_address = server_address
        self.timeout = timeout
        self.window_size = window_size
        self.unacked_messages = {}  # Tracks unacknowledged messages by sequence number
        self.next_seq_num = 0  # Sequence number for the next message to send
        self.base = 0  # Sequence number of the oldest unacknowledged message
        self.timer = None  # Timer for handling retransmission on timeout
        self.reset_parameters() # Reset the parameters above for a new message

    # This function starts the timer
    def start_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = Timer(self.timeout, self.handle_timeout)
        self.timer.start()

    """
    Reset the client parameters for a new message transmission.
    """
    def reset_parameters(self):

        self.unacked_messages = {}  # Tracks unacknowledged messages by sequence number
        self.next_seq_num = 0  # Sequence number for the next message to send
        self.base = 0  # Sequence number of the oldest unacknowledged message
        self.timer = None  # Timer for handling retransmission on timeout

    # This function stops the timer
    def stop_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

    # This function handles timeout
    def handle_timeout(self):
        print(f"Timeout expired. Retransmitting from sequence number {self.base}.")
        self.retransmit_unacked_messages()
        self.start_timer()

    # This function retransmits messages that did not receive ACK (from window)
    def retransmit_unacked_messages(self):
        for seq_num in range(self.base, self.next_seq_num):
            if seq_num in self.unacked_messages:
                chunk = self.unacked_messages[seq_num]
                self.send_message(chunk)

    # This function sends a message to the server
    def send_message(self, message: str):
        if self.client_socket: # Check if client's socket active
            try:
                self.client_socket.sendall(message.encode('utf-8'))
            except OSError as e:
                print(f"Error sending message: {e}")
                self.stop_timer()
        else:
            print("Socket is closed. Cannot send message.")


    """
    This function manages the sliding window logic and sends chunks in the correct order.
    Function's responsibility:
    1. Divide message into chunks (given max_size).
    2. Sending chunks in order while handing the sliding window.
    3. Retransmit unacked messages if timeout expires / we got ACK out of order.
    """
    def run(self, message: str, max_size: int, max_retries: int = 5):
        self.reset_parameters()

        # Divide message into chunks
        chunks = [
            f"M{i}:{message[i * max_size:(i + 1) * max_size]}"
            for i in range((len(message) + max_size - 1) // max_size)
        ]
        total_chunks = len(chunks) # number of chunks
        print(f"Total chunks to send: {total_chunks}")

        retry_count = 0  # Counter for retries on unacknowledged chunks.

        try:
            # Send chunks with sliding window.
            while self.base < total_chunks:
                # Send chunks within the current window.
                while self.next_seq_num < self.base + self.window_size and self.next_seq_num < total_chunks:
                    chunk = chunks[self.next_seq_num] # Current chunk.
                    self.unacked_messages[self.next_seq_num] = chunk # Adding chunk to the unacked msg list.
                    print(f"Sending: {chunk}")
                    self.send_message(chunk) # Send current chunk.
                    if self.base == self.next_seq_num:
                        self.start_timer()  # Start timer for the oldest unacknowledged chunk.
                    self.next_seq_num += 1

                try:
                    # Wait for acknowledgments
                    ack = self.client_socket.recv(1024).decode('utf-8')
                    acks = ack.split("ACK")  # Split by "ACK"
                    for ack in acks:
                        if ack.strip():  # Ignore empty parts
                            try:
                                ack_num = int(ack.strip())  # Parse the acknowledgment number
                                print(f"Received ACK for M{ack_num}")

                                if ack_num >= self.base:
                                    # Mark received ACKs and check for contiguous acknowledgment
                                    while self.base in self.unacked_messages:
                                        if ack_num == self.base:  # If the base is acknowledged
                                            del self.unacked_messages[self.base]
                                            self.base += 1
                                        else:
                                            break  # Stop if there’s a gap in acknowledgment

                                    if self.base == self.next_seq_num:
                                        self.stop_timer()  # Stop timer if all chunks are acknowledged
                                    else:
                                        self.start_timer()  # Restart timer for the next unacknowledged chunk

                                    retry_count = 0  # Reset retry count on successful acknowledgment
                                else:
                                    print(f"Ignoring duplicate ACK for M{ack_num}.")
                            except ValueError:
                                print(f"Error parsing ACK: {ack.strip()}")  # Handle invalid ACK format
                except socket.timeout: # Timeout expired. handling timeout exception
                    retry_count += 1
                    if retry_count > max_retries:
                        print(f"Maximum retries reached. Aborting transmission.")
                        break  # Stop retransmissions after max retries
                    self.retransmit_unacked_messages()
        except Exception as e:
            print(f"Error during message transmission: {e}")
        finally:
            self.stop_timer()  # Ensure the timer is stopped
            print("Message transmission ended.")


### **Main Client Function**
def client(server_address: tuple[str, int]):
    # Prompt user to choose the source of the initial message
    input_choice = input("Please provide the message for max_size and input window size and timeout preferences from:\n"
                         "1. Manual Input\n"
                         "2. File Input\n").strip()

    if input_choice == '1':
        # Prompt user to enter timeout in seconds.
        timeout = float(input("Enter timeout (seconds): ").strip())
        # Prompt user to enter window size.
        window_size = int(input("Enter window size: ").strip())
        # Construct the message manually.
        message = (
            "message:\"REQUEST_MAX_SIZE_MANUAL\"\n"
            f"maximum_msg_size:0\n"
            f"window_size: {window_size}\n"
            f"timeout: {timeout}\n"
        )
    elif input_choice == '2':
        file_path = select_file()  # Open file explorer to select a file.
        if not file_path: # User did not select a file to transmit.
            print("No file selected. Returning to main menu.")
            return
        try:
            params = parse_request_file(file_path)
            # Extract parameters from the parsed dictionary
            message = (
                f"message:\"{params['message']} REQUEST_MAX_SIZE_FILE\"\n"
                f"maximum_msg_size: {params['maximum_msg_size']}\n"
                f"window_size: {params['window_size']}\n"
                f"timeout: {params['timeout']}\n"
            )
            timeout = params['timeout']
            window_size = params['window_size']
            print(f"Request loaded and parsed successfully:\n{message}")
        except Exception as e:
            print(f"Error: {e}")
            return
    else:
        print("Invalid choice.")
        return

    # Initialize client instance
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.settimeout(timeout)
    client_instance = Client(server_address, timeout, window_size)
    client_instance.client_socket = client_socket

    try:
        # Connect to server
        client_socket.connect(server_address)
        print(f"Connected to server at {server_address[0]}:{server_address[1]}")

        # Send the initial request to the server
        client_socket.sendall(message.encode('utf-8'))
        print("Request sent to server.")

        # Receive and decode the maximum message size
        max_size = int(client_socket.recv(1024).decode('utf-8'))
        print(f"Maximum message size received from server: {max_size}")

        # Main loop for sending messages
        while True:
            # Prompt user for next action
            choice = input(
                "Please choose a message to send to the server:"
                "\n1. Input a message manually."
                "\n2. Load from a .txt file."
                "\n3. Close connection.\n").strip()

            if choice == '1':  # Prompt user for the message
                message = input("Enter your message: ").strip()

            elif choice == '2':  # Load the message from a file
                file_path = select_file()  # Open file explorer to select a file
                if not file_path:
                    print("No file selected. Returning to main menu.")
                    return
                try:
                    params = parse_request_file(file_path)
                    # Extract the message from the parsed dictionary
                    message = params['message']
                    print(f"Message loaded successfully:\n{message}")
                except FileNotFoundError:
                    print("Error: File not found. Please try again.")
                    continue
                except Exception as e:
                    print(f"Error: reading file: {e}. Please try again.")
                    continue
            elif choice == '3':  # Close the connection
                print("Closing connection to the server.")
                break
            else:
                print("Invalid choice. Please enter '1', '2', or '3'.")
                continue

            # Run the client logic to send the message
            client_instance.run(message, max_size)

    finally:
        if client_socket.timeout == 0:
            print("Connection timed out.")
        client_socket.close()
        print("Connection closed.")


if __name__ == "__main__":
    # Set up argument parser
    arg_parser = argparse.ArgumentParser(description="A Sliding Window Client.")

    arg_parser.add_argument("-p", "--port", type=int,
                            default=DEFAULT_SERVER_PORT, help="The port to connect to.")
    arg_parser.add_argument("-H", "--host", type=str,
                            default=DEFAULT_SERVER_HOST, help="The host to connect to.")

    args = arg_parser.parse_args()

    # Use parsed arguments or defaults
    host = args.host
    port = args.port

    # Start the client with the specified host and port
    client((host, port))
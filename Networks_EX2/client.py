import socket
import api
import argparse

# region Predefined

# The following are for convenience. You can use them to build expressions.
pi_c = api.NAMED_CONSTANTS.PI
tau_c = api.NAMED_CONSTANTS.TAU
e_c = api.NAMED_CONSTANTS.E

add_b = api.BINARY_OPERATORS.ADD
sub_b = api.BINARY_OPERATORS.SUB
mul_b = api.BINARY_OPERATORS.MUL
div_b = api.BINARY_OPERATORS.DIV
mod_b = api.BINARY_OPERATORS.MOD
pow_b = api.BINARY_OPERATORS.POW

neg_u = api.UNARY_OPERATORS.NEG
pos_u = api.UNARY_OPERATORS.POS

sin_f = api.FUNCTIONS.SIN
cos_f = api.FUNCTIONS.COS
tan_f = api.FUNCTIONS.TAN
sqrt_f = api.FUNCTIONS.SQRT
log_f = api.FUNCTIONS.LOG
max_f = api.FUNCTIONS.MAX
min_f = api.FUNCTIONS.MIN
pow_f = api.FUNCTIONS.POW
rand_f = api.FUNCTIONS.RAND

# endregion


def process_response(response: api.CalculatorHeader) -> None:
    if response.is_request:
        raise api.CalculatorClientError("Got a request instead of a response")
    if response.status_code == api.CalculatorHeader.STATUS_OK:
        result, steps = api.data_to_result(response)
        print("Result:", result)
        if steps:
            print("Steps:")
            expr, first, *rest = steps
            print(f"{expr} = {first}", end="\n"*(not bool(rest)))
            if rest:
                print(
                    "".join(map(lambda v: f"\n{' ' * len(expr)} = {v}", rest)))
    elif response.status_code == api.CalculatorHeader.STATUS_CLIENT_ERROR:
        err = api.data_to_error(response)
        raise api.CalculatorClientError(err)
    elif response.status_code == api.CalculatorHeader.STATUS_SERVER_ERROR:
        err = api.data_to_error(response)
        raise api.CalculatorServerError(err)
    else:
        raise api.CalculatorClientError(
            f"Unknown status code: {response.status_code}")


def client(server_address: tuple[str, int], expression: api.Expression, show_steps: bool = False, cache_result: bool = False, cache_control: int = api.CalculatorHeader.MAX_CACHE_CONTROL) -> None:
    server_prefix = f"{{{server_address[0]}:{server_address[1]}}}"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        client_socket.connect((server_address ,port))
        print(f"{server_prefix} Connection established")
        try:
            while True:
                # Display options to the user
                print("Choose an expression to calculate:")
                print("1: '(sin(max(2, 3 * 4, 5, 6 * ((7 * 8) / 9), 10 / 11)) / 12) * 13'")
                print("2: '(max(2, 3) + 3)'")
                print("3: '3 + ((4 * 2) / ((1 - 5) ** (2 ** 3)))'")
                print("4: '((1 + 2) ** (3 * 4)) / (5 * 6)'")
                print("5: '-(-((1 + (2 + 3)) ** -(4 + 5)))'")
                print("6: 'max(2, (3 * 4), log(e), (6 * 7), (9 / 8))'")
                print("7: Exit")

                choice = input("Enter your choice: ")

                if choice == "1":
                    expr = mul_b(div_b(sin_f(max_f(2, mul_b(3, 4), 5, mul_b(6, div_b(mul_b(7, 8), 9)), div_b(10, 11))), 12), 13)
                elif choice == "2":
                    expr = add_b(max_f(2, 3), 3)
                elif choice == "3":
                    expr = add_b(3, div_b(mul_b(4, 2), pow_b(sub_b(1, 5), pow_b(2, 3))))
                elif choice == "4":
                    expr = div_b(pow_b(add_b(1, 2), mul_b(3, 4)), mul_b(5, 6))
                elif choice == "5":
                    expr = neg_u(neg_u(pow_b(add_b(1, add_b(2, 3)), neg_u(add_b(4, 5)))))
                elif choice == "6":
                    expr = max_f(2, mul_b(3, 4), log_f(e_c), mul_b(6, 7), div_b(9, 8))
                elif choice == "7":
                    print("Exiting...")
                    client_socket.sendall(api.CalculatorHeader.from_request(
                        b"exit", show_steps, cache_result, cache_control).pack())
                    break
                else:
                    print("Invalid choice. Please try again.")
                    continue

                # Parameters for the calculation
                show_steps = True  # Request the steps of the calculation
                cache_result = True  # Request to cache the result of the calculation
                cache_control = 2**16 - 1  # Maximum age of the cached response

                # Send request to the server
                request = api.CalculatorHeader.from_expression(
                    expr, show_steps, cache_result, cache_control)
                client_socket.sendall(request.pack())

                # Receive response from the server
                response = client_socket.recv(api.BUFFER_SIZE)
                response = api.CalculatorHeader.unpack(response)
                process_response(response)

        except api.CalculatorError as e:
            print(f"{server_prefix} Got error: {str(e)}")
        except Exception as e:
            print(f"{server_prefix} Unexpected error: {str(e)}")
    print(f"{server_prefix} Connection closed")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="A Calculator Client.")

    arg_parser.add_argument("-p", "--port", type=int,
                            default=api.DEFAULT_SERVER_PORT, help="The port to connect to.")
    arg_parser.add_argument("-H", "--host", type=str,
                            default=api.DEFAULT_SERVER_HOST, help="The host to connect to.")

    args = arg_parser.parse_args()

    host = args.host
    port = args.port

    # Start the client
    client((host, port), None)
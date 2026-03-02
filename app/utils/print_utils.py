from colorama import Fore, Style, Back
from colorama import init as colorama_init

colorama_init()


def printStat(status: str, input: str):

    crit: str = "c"
    problem: str = "p"
    warn: str = "w"
    ok: str = "o"

    if status == crit:
        print(f"{Back.LIGHTRED_EX}{Fore.BLACK}[CRITICAL]{Style.RESET_ALL}==> {input}")
    elif status == problem:
        print(f"{Back.YELLOW}{Fore.BLACK}[PROBLEM]{Style.RESET_ALL}==> {input}")
    elif status == warn:
        print(f"{Back.YELLOW}{Fore.BLACK}[WARNING]{Style.RESET_ALL}==> {input}")
    elif status == ok:
        print(f"{Back.GREEN}{Fore.BLACK}[OK]{Style.RESET_ALL}{Style.DIM}==> {input}{Style.RESET_ALL}")
    else:
        print(
            f"{Style.DIM}Bad input to printStat. Proceeding to print raw info below.){Style.RESET_ALL}"
        )
        print(input)

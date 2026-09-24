import os
import sys

def verify_chosen_config():
    config_file = 'results_phase2/chosen_config.txt'
    if not os.path.exists(config_file):
        print("ERROR: chosen_config.txt not found")
        return False
    with open(config_file, 'r') as f:
        content = f.read().strip()
    print("Chosen config content:", content)
    if "MF=0.0004" in content and "Priority 1" in content:
        print("PASS: Chosen config is MF=0.0004 with Priority 1 reasoning")
        return True
    else:
        print("FAIL: Chosen config does not match expected MF=0.0004 and Priority 1")
        return False

def verify_statistical_tests_mf0_0004():
    stats_file = 'results_phase2/statistical_tests_output.txt'
    if not os.path.exists(stats_file):
        print("ERROR: statistical_tests_output.txt not found")
        return False
    with open(stats_file, 'r') as f:
        content = f.read()
    hac_p = None
    dsr_survives = None
    for line in content.split('\n'):
        if 'NEWEY-WEST HAC' in line or 'Newey-West HAC' in line:
            import re
            match = re.search(r'p-value=([0-9.]+)', line)
            if match:
                hac_p = float(match.group(1))
        if 'Survives (p < 0.05)?' in line:
            if 'True' in line:
                dsr_survives = True
            else:
                dsr_survives = False
    print(f"HAC p-value: {hac_p}")
    print(f"DSR survives: {dsr_survives}")
    if hac_p is not None and hac_p < 0.05 and dsr_survives is True:
        print("PASS: MF=0.0004 passes HAC significance and DSR survives")
        return True
    else:
        print("FAIL: MF=0.0004 does not pass both HAC significance and DSR survival")
        print(f"  Details: hac_p={hac_p}, hac_p<0.05={hac_p is not None and hac_p < 0.05}, dsr_survives={dsr_survives}")
        return False

def verify_walk_forward_includes_all_mf():
    wf_file = 'results_phase2/walk_forward_funding.txt'
    if not os.path.exists(wf_file):
        print("ERROR: walk_forward_funding.txt not found")
        return False
    with open(wf_file, 'r') as f:
        content = f.read()
    if 'MF candidates: [0.0002, 0.0003, 0.0004, 0.0005]' in content:
        print("PASS: Walk-forward includes all MF candidates")
        lines = content.split('\n')
        best_mfs = set()
        for line in lines:
            if line.strip().startswith('Window') or line.strip() == '' or line.startswith('-'):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    mf = float(parts[1])
                    best_mfs.add(mf)
                except:
                    pass
        print(f"Unique best MFs observed: {sorted(best_mfs)}")
        if len(best_mfs) > 1:
            print("PASS: Multiple MFs selected as best across windows")
        else:
            print("WARNING: Only one MF selected as best across windows (but still testing all)")
        return True
    else:
        print("FAIL: Walk-forward does not list all four MF candidates")
        return False

def verify_readme_mf0_0004_numbers():
    readme_file = 'README.md'
    if not os.path.exists(readme_file):
        print("ERROR: README.md not found")
        return False
    with open(readme_file, 'r', encoding='utf-8') as f:
        content = f.read()
    expected = {
        'Trades/month': '25.22',
        'Net PnL': '22.19%',
        'Sharpe': '2.58',
        'Max drawdown': '-2.19%'
    }
    all_found = True
    for label, val in expected.items():
        if val not in content:
            print(f"FAIL: Expected '{val}' for '{label}' not found in README")
            all_found = False
        else:
            print(f"PASS: Found '{val}' for '{label}'")
    return all_found

def main():
    print("=== Ad-hoc verification of fixes for MF=0.0004 ===\n")
    all_pass = True
    all_pass &= verify_chosen_config()
    print()
    all_pass &= verify_statistical_tests_mf0_0004()
    print()
    all_pass &= verify_walk_forward_includes_all_mf()
    print()
    all_pass &= verify_readme_mf0_0004_numbers()
    print()
    if all_pass:
        print("=== ALL CHECKS PASSED ===")
    else:
        print("=== SOME CHECKS FAILED ===")
    return all_pass

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
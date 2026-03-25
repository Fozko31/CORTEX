import subprocess, sys

tests = [
    "tests/test_b1_surfsense_health.py",
    "tests/test_b2_surfsense_auth.py",
    "tests/test_b3_surfsense_spaces.py",
    "tests/test_b4_surfsense_push.py",
    "tests/test_b5_zep_health.py",
    "tests/test_b6_model_router.py",
]

print("=" * 60)
print("RUNNING ALL PHASE B TESTS - POST FIX")
print("=" * 60)
print()

all_pass = True
results = {}

for t in tests:
    test_name = t.split("/")[-1].replace(".py", "")
    print(f"Running {test_name}...", end=" ", flush=True)
    
    r = subprocess.run(
        [sys.executable, "-W", "ignore", t],
        capture_output=True, text=True, cwd=r"C:\Users\Admin\CORTEX"
    )
    
    passed = r.returncode == 0
    results[test_name] = passed
    
    if passed:
        print("[PASS]")
    else:
        print("[FAIL]")
        all_pass = False

print()
print("=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)
for test_name, passed in results.items():
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} — {test_name}")

print()
if all_pass:
    print("ALL TESTS PASSED!")
    sys.exit(0)
else:
    print("SOME TESTS FAILED — check individual outputs")
    sys.exit(1)

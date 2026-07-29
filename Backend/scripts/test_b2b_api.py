"""
TrustAgent — B2B API Quick Test Script

Chạy file này để test endpoint B2B trước khi gửi cho đối tác:
    python Backend/scripts/test_b2b_api.py

Hoặc test trên server đã deploy:
    python Backend/scripts/test_b2b_api.py --url https://trustagent-api.onrender.com
"""

import argparse
import json
import sys
import time

# Fix UTF-8 encoding on Windows PowerShell
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    import requests
except ImportError:
    print("Cai requests truoc: pip install requests")
    sys.exit(1)


# Màu sắc terminal
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

TEST_CASES = [
    {
        "name": "OK Bao ve du lieu hop le",
        "description": "He thong xu ly du lieu ten, email cua 500 nhan vien de quan ly nhan su. Da co phan quyen truy cap, ma hoa du lieu, va ghi log day du.",
        "expect_compliant": True,
    },
    {
        "name": "FAIL Phat vi pham vuot 8%",
        "description": "Hop dong cung cap dich vu tu van 100 trieu VND. Dieu khoan phat vi pham la 15 trieu VND (vuot 8%).",
        "expect_compliant": False,
    },
    {
        "name": "FAIL Xu ly van tay chua phan quyen",
        "description": "He thong AI xu ly du lieu van tay cua 2000 nhan vien de cham cong, chua thiet lap phan quyen truy cap.",
        "expect_compliant": False,
    },
    {
        "name": "FAIL Trai phieu chua cong bo dung han",
        "description": "Doanh nghiep phat hanh trai phieu, nhung sau 7 ngay van chua cong bo thong tin tren thi truong.",
        "expect_compliant": False,
    },
]


def run_tests(base_url: str, api_key: str = ""):
    print(f"\n{BOLD}{'='*65}{RESET}")
    print(f"{BOLD}🛡️  TrustAgent B2B API — Integration Test{RESET}")
    print(f"{BOLD}{'='*65}{RESET}")
    print(f"Server: {CYAN}{base_url}{RESET}")
    print()

    # 1. Health check
    print(f"{YELLOW}[1/2] Health check...{RESET}")
    try:
        r = requests.get(f"{base_url}/api/v1/audit/health", timeout=10)
        if r.status_code == 200:
            print(f"{GREEN}✅ Server OK{RESET}: {r.json().get('service')}")
        else:
            print(f"{RED}❌ Server không phản hồi đúng: {r.status_code}{RESET}")
            return
    except Exception as e:
        print(f"{RED}❌ Không kết nối được server: {e}{RESET}")
        return

    # 2. Audit tests
    print(f"\n{YELLOW}[2/2] Chạy {len(TEST_CASES)} test cases...{RESET}\n")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key

    passed = 0
    for i, tc in enumerate(TEST_CASES, 1):
        print(f"Test {i}: {tc['name']}")
        print(f"  Input: \"{tc['description'][:70]}...\"")

        t_start = time.time()
        try:
            r = requests.post(
                f"{base_url}/api/v1/audit",
                json={"description": tc["description"]},
                headers=headers,
                timeout=30,
            )
            elapsed = (time.time() - t_start) * 1000

            if r.status_code != 200:
                print(f"  {RED}❌ HTTP {r.status_code}: {r.text[:100]}{RESET}\n")
                continue

            data = r.json()
            is_compliant = data.get("is_compliant", False)
            z3 = data.get("z3_status", "?")
            violations = data.get("violations", [])
            dur = data.get("duration_ms", elapsed)

            ok = is_compliant == tc["expect_compliant"]
            status_icon = f"{GREEN}✅ PASS{RESET}" if ok else f"{RED}❌ FAIL{RESET}"
            compliant_str = f"{GREEN}HỢP LỆ{RESET}" if is_compliant else f"{RED}VI PHẠM{RESET}"

            print(f"  Kết quả:  {compliant_str} | Z3={CYAN}{z3}{RESET} | {len(violations)} vi phạm | {dur:.0f}ms")
            if violations:
                for v in violations[:2]:
                    print(f"    → [{v.get('severity','?').upper()}] {v.get('detail', '')[:70]}")
            print(f"  Test:     {status_icon}")

            if ok:
                passed += 1

        except Exception as e:
            print(f"  {RED}❌ Lỗi: {e}{RESET}")

        print()

    # Summary
    print(f"{BOLD}{'='*65}{RESET}")
    print(f"Kết quả: {GREEN}{passed}{RESET}/{len(TEST_CASES)} tests passed")
    if passed == len(TEST_CASES):
        print(f"{GREEN}{BOLD}🎉 Tất cả tests PASSED! API sẵn sàng cho đối tác.{RESET}")
    else:
        print(f"{YELLOW}⚠️  Một số test thất bại — kiểm tra log server.{RESET}")
    print(f"{BOLD}{'='*65}{RESET}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TrustAgent B2B API Test")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL của server (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--key",
        default="",
        help="API key (nếu cần)",
    )
    args = parser.parse_args()

    run_tests(base_url=args.url.rstrip("/"), api_key=args.key)

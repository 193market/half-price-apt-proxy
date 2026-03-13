"""
반값아파트 찾기 — 공공API 프록시 서버
포트: 환경변수 PORT (기본 8090)
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import json
import re
import os
from datetime import datetime, timedelta

SERVICE_KEY = "xsG0WMPtWS1mUarzKPkfhWjUUvyKIqfBF34M5NHtM7PcQykB9r9bfji96dhrfkH0peDerZ6iDfVqwSoYS9SEcQ=="
PORT = int(os.environ.get("PORT", 8090))

APIS = {
    # LH 임대주택단지 조회
    "lh_complexes": "http://apis.data.go.kr/B552555/lhLeaseInfo1/lhLeaseInfo1",
    # LH 분양임대공고문 조회 (올바른 엔드포인트)
    "lh_announcements": "http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1",
    # LH 공고 상세
    "lh_announcement_detail": "http://apis.data.go.kr/B552555/lhLeaseNoticeDetail1/lhLeaseNoticeDetail1",
    # 마이홈포털 공공주택 모집공고
    "myhome_announcements": "http://apis.data.go.kr/1613000/AptHousePublicOfferSvc/getPblancList",
    # 아파트 전월세 실거래가
    "realprice_apt": "http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
    # 연립다세대 전월세 실거래가
    "realprice_multi": "http://apis.data.go.kr/1613000/RTMSDataSvcRHRent/getRTMSDataSvcRHRent",
}

def fetch_api(base_url, params):
    params["serviceKey"] = SERVICE_KEY
    params["_type"] = "json"
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"{base_url}?{query}"
    print(f"[API] {url[:100]}...")
    try:
        with urllib.request.urlopen(url, timeout=10) as res:
            raw = res.read().decode("utf-8")
            # JSON 파싱 시도
            try:
                return json.loads(raw)
            except:
                # XML 응답인 경우 간단 파싱
                return {"raw": raw}
    except Exception as e:
        return {"error": str(e)}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = dict(urllib.parse.parse_qsl(parsed.query))

        # ── LH 임대단지 목록
        if path == "/api/lh/complexes":
            params = {
                "PG_SZ": qs.get("size", "20"),
                "PAGE": qs.get("page", "1"),
            }
            if qs.get("region"): params["CNP_CD"] = qs["region"]
            if qs.get("type"):   params["SPL_TP_CD"] = qs["type"]
            data = fetch_api(APIS["lh_complexes"], params)
            self.send_json(self._parse_lh_complexes(data))

        # ── LH 분양임대공고 목록
        elif path == "/api/lh/announcements":
            today = datetime.now()
            past = (today - timedelta(days=90)).strftime("%Y.%m.%d")
            future = (today + timedelta(days=90)).strftime("%Y.%m.%d")
            params = {
                "PG_SZ": qs.get("size", "20"),
                "PAGE":  qs.get("page", "1"),
                "PAN_NT_ST_DT": past,
                "CLSG_DT": future,
                "PAN_SS": "공고중",
            }
            data = fetch_api(APIS["lh_announcements"], params)
            self.send_json(self._parse_lh_announcements(data))

        # ── LH 공고 상세
        elif path.startswith("/api/lh/announcement/"):
            notice_id = path.split("/")[-1]
            data = fetch_api(APIS["lh_announcement_detail"], {"PAN_ID": notice_id})
            self.send_json(data)

        # ── 마이홈포털 공고
        elif path == "/api/myhome/announcements":
            params = {
                "numOfRows": qs.get("size", "20"),
                "pageNo":    qs.get("page", "1"),
            }
            data = fetch_api(APIS["myhome_announcements"], params)
            self.send_json(self._parse_myhome(data))

        # ── 아파트 전월세 실거래가
        elif path == "/api/realprice/apt":
            params = {
                "LAWD_CD":  qs.get("region", "11110"),
                "DEAL_YMD": qs.get("ym", "202502"),
                "numOfRows": "100",
            }
            data = fetch_api(APIS["realprice_apt"], params)
            self.send_json(self._parse_realprice(data))

        # ── 연립다세대 전월세 실거래가
        elif path == "/api/realprice/multi":
            params = {
                "LAWD_CD":  qs.get("region", "11110"),
                "DEAL_YMD": qs.get("ym", "202502"),
                "numOfRows": "100",
            }
            data = fetch_api(APIS["realprice_multi"], params)
            self.send_json(self._parse_realprice(data))

        # ── 헬스체크
        elif path == "/health":
            self.send_json({"status": "ok", "port": PORT})

        else:
            self.send_json({"error": "not found"}, 404)

    # ── 파서들
    def _parse_lh_complexes(self, data):
        try:
            # API returns a list: [{dsSch:[...]}, {dsList:[...items...], resHeader:{...}}]
            items = []
            if isinstance(data, list):
                for part in data:
                    if isinstance(part, dict) and "dsList" in part:
                        items = part["dsList"]
                        break
            elif isinstance(data, dict):
                items = data.get("dsList", [{}])[0].get("row", [])
            return {
                "items": [{
                    "id":       r.get("SBD_CD", ""),
                    "name":     r.get("SBD_LGO_NM", ""),
                    "region":   r.get("ARA_NM", ""),
                    "type":     r.get("AIS_TP_CD_NM", ""),
                    "units":    r.get("SUM_HSH_CNT", 0),
                    "area":     r.get("DDO_AR", 0),
                    "deposit":  int(r.get("LS_GMY", 0) or 0) // 10000,  # 원→만원
                    "rent":     int(r.get("RFE", 0) or 0) // 10000,      # 원→만원
                    "moveIn":   r.get("MVIN_XPC_YM", ""),
                } for r in items],
                "total": len(items)
            }
        except:
            return {"items": [], "total": 0, "raw": data}

    def _parse_lh_announcements(self, data):
        try:
            items = []
            if isinstance(data, list):
                for part in data:
                    if isinstance(part, dict) and "dsList" in part:
                        items = part["dsList"]
                        break
            elif isinstance(data, dict):
                for key in ["dsList", "items"]:
                    if key in data:
                        items = data[key]
                        break
            return {
                "items": [{
                    "id":        r.get("PAN_ID", ""),
                    "title":     r.get("PAN_NM", ""),
                    "type":      r.get("AIS_TP_CD_NM", r.get("UPP_AIS_TP_NM", "")),
                    "startDate": r.get("PAN_NT_ST_DT", ""),
                    "endDate":   r.get("CLSG_DT", ""),
                    "region":    r.get("CNP_CD_NM", ""),
                    "status":    r.get("PAN_SS", ""),
                    "url":       r.get("DTL_URL", ""),
                } for r in items],
                "total": len(items)
            }
        except:
            return {"items": [], "total": 0}

    def _parse_myhome(self, data):
        try:
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if isinstance(items, dict): items = [items]
            return {
                "items": [{
                    "id":        i.get("pblancNo", ""),
                    "title":     i.get("pblancNm", ""),
                    "type":      i.get("hssplyCtprvnNm", ""),
                    "startDate": str(i.get("rcritPblancDe", "")),
                    "endDate":   str(i.get("przwnnPresnatnDe", "")),
                } for i in items],
                "total": len(items)
            }
        except:
            return {"items": [], "total": 0}

    def _parse_realprice(self, data):
        try:
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if isinstance(items, dict): items = [items]
            rents = [int(str(i.get("월세금액", i.get("monthlyRent", 0))).replace(",", "") or 0)
                     for i in items if i.get("월세금액") or i.get("monthlyRent")]
            avg = int(sum(rents) / len(rents)) if rents else 0
            return {
                "avgMonthlyRent": avg,   # 단위: 만원
                "count": len(rents),
                "items": items[:10]
            }
        except:
            return {"avgMonthlyRent": 0, "count": 0}

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[OK] Proxy server started -> http://localhost:{PORT}")
    print("   종료: Ctrl+C")
    server.serve_forever()

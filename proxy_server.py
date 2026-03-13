"""
반값아파트 찾기 — 공공API 프록시 서버 v2.0
포트: 환경변수 PORT (기본 8090)

API 출처 (02_데이터 문서 기반):
- LH 임대단지:      http://apis.data.go.kr/B552555/lhLeaseInfo1/lhLeaseInfo1
- 마이홈 단지:      https://apis.data.go.kr/1613000/HWSPR04/rentalHouseGwList
- LH 일반공고:      http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1
- LH 사전청약공고:  http://apis.data.go.kr/B552555/lhLeaseNoticeBfhInfo1/lhLeaseNoticeBfhInfo1
- 아파트 전월세:    http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import json
import os
from datetime import datetime, timedelta

SERVICE_KEY = "xsG0WMPtWS1mUarzKPkfhWjUUvyKIqfBF34M5NHtM7PcQykB9r9bfji96dhrfkH0peDerZ6iDfVqwSoYS9SEcQ=="
PORT = int(os.environ.get("PORT", 8090))

APIS = {
    "lh_complexes":      "http://apis.data.go.kr/B552555/lhLeaseInfo1/lhLeaseInfo1",
    "myhome_complexes":  "https://apis.data.go.kr/1613000/HWSPR04/rentalHouseGwList",
    "lh_notice":         "http://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1",
    "lh_notice_pre":     "http://apis.data.go.kr/B552555/lhLeaseNoticeBfhInfo1/lhLeaseNoticeBfhInfo1",
    "realprice_apt":     "http://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
}

def fetch_api(base_url, params):
    params["serviceKey"] = SERVICE_KEY
    params["_type"] = "json"
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"{base_url}?{query}"
    print(f"[API] {url[:120]}...")
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read().decode("utf-8")
            try:
                return json.loads(raw)
            except Exception:
                return {"raw": raw[:500]}
    except Exception as e:
        return {"error": str(e)}

def _date_str(delta_days=0, fmt="%Y.%m.%d"):
    return (datetime.now() + timedelta(days=delta_days)).strftime(fmt)

def _extract_dsList(data):
    """LH API의 dsList 추출 — list 또는 dict 응답 모두 처리"""
    if isinstance(data, list):
        # 형태: [{dsSch:{...}}, {dsList:[...], resHeader:{...}}]
        for part in data:
            if isinstance(part, dict) and "dsList" in part:
                ds = part["dsList"]
                return ds if isinstance(ds, list) else [ds]
    elif isinstance(data, dict):
        ds = data.get("dsList")
        if ds is not None:
            return ds if isinstance(ds, list) else [ds]
    return []

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

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
        path   = parsed.path
        qs     = dict(urllib.parse.parse_qsl(parsed.query))

        # ── LH 임대단지 목록 (CNP_CD 지역 필터 지원)
        if path == "/api/lh/complexes":
            params = {
                "PG_SZ": qs.get("size", "30"),
                "PAGE":  qs.get("page", "1"),
            }
            if qs.get("region"): params["CNP_CD"]     = qs["region"]
            if qs.get("type"):   params["SPL_TP_CD"]  = qs["type"]
            data = fetch_api(APIS["lh_complexes"], params)
            self.send_json(self._parse_lh_complexes(data))

        # ── 마이홈포털 단지 목록 (brtcCode+signguCode 필수)
        elif path == "/api/myhome/complexes":
            params = {
                "brtcCode":  qs.get("brtcCode", "11"),
                "signguCode": qs.get("signguCode", "110"),
                "numOfRows": qs.get("size", "30"),
                "pageNo":    qs.get("page", "1"),
            }
            data = fetch_api(APIS["myhome_complexes"], params)
            self.send_json(self._parse_myhome_complexes(data))

        # ── LH 일반 공고 (PAN_NT_ST_DT·CLSG_DT 필수)
        elif path == "/api/lh/notices":
            params = {
                "PG_SZ":        qs.get("size", "20"),
                "PAGE":         qs.get("page", "1"),
                "PAN_NT_ST_DT": qs.get("startDate", _date_str(-90)),
                "CLSG_DT":      qs.get("endDate",   _date_str(90)),
                "PAN_SS":       qs.get("status",    "공고중"),
            }
            if qs.get("region"): params["CNP_CD"] = qs["region"]
            data = fetch_api(APIS["lh_notice"], params)
            self.send_json(self._parse_lh_notices(data))

        # ── LH 사전청약 공고 (PAN_ST_DT·PAN_ED_DT 필수)
        elif path == "/api/lh/notices/pre":
            params = {
                "PG_SZ":      qs.get("size", "20"),
                "PAGE":       qs.get("page", "1"),
                "PAN_ST_DT":  qs.get("startDate", _date_str(-90)),
                "PAN_ED_DT":  qs.get("endDate",   _date_str(90)),
                "PAN_SS":     qs.get("status",    "공고중"),
            }
            data = fetch_api(APIS["lh_notice_pre"], params)
            self.send_json(self._parse_lh_notices(data))

        # ── 아파트 전월세 실거래가 (시세 비교용)
        elif path == "/api/realprice/apt":
            params = {
                "LAWD_CD":   qs.get("region", "11110"),
                "DEAL_YMD":  qs.get("ym", datetime.now().strftime("%Y%m")),
                "numOfRows": "100",
            }
            data = fetch_api(APIS["realprice_apt"], params)
            self.send_json(self._parse_realprice(data))

        # ── 헬스체크
        elif path == "/health":
            self.send_json({"status": "ok", "port": PORT})

        else:
            self.send_json({"error": "not found"}, 404)

    # ────────────────────────────────────────────────────
    # 파서: LH 임대단지
    # 응답: [{dsSch:{...}}, {dsList:[{SBD_LGO_NM, ARA_NM, AIS_TP_CD_NM,
    #         SUM_HSH_CNT, DDO_AR, LS_GMY(원), RFE(원), MVIN_XPC_YM},...]}]
    # ────────────────────────────────────────────────────
    def _parse_lh_complexes(self, data):
        try:
            rows = _extract_dsList(data)
            return {
                "items": [{
                    "id":      r.get("SBD_CD", ""),
                    "name":    r.get("SBD_LGO_NM", ""),
                    "region":  r.get("ARA_NM", ""),
                    "type":    r.get("AIS_TP_CD_NM", ""),
                    "units":   r.get("SUM_HSH_CNT", 0),
                    "area":    r.get("DDO_AR", 0),
                    "deposit": int(r.get("LS_GMY", 0) or 0) // 10000,  # 원→만원
                    "rent":    int(r.get("RFE", 0) or 0) // 10000,      # 원→만원
                    "moveIn":  r.get("MVIN_XPC_YM", ""),
                    "addr":    r.get("LGO_ADR", ""),
                } for r in rows],
                "total": len(rows)
            }
        except Exception as e:
            return {"items": [], "total": 0, "debug": str(e)}

    # ────────────────────────────────────────────────────
    # 파서: 마이홈포털 단지
    # 응답: {"header":{...}, "body":{"item":[{hsmpNm, brtcNm, signguNm,
    #         suplyTyNm, suplyPrvuseAr, hshldCo, bassRentGtn(원), bassMtRntchrg(원),
    #         competDe, rnAdres}]}}
    # ────────────────────────────────────────────────────
    def _parse_myhome_complexes(self, data):
        try:
            body  = data.get("body", {})
            items = body.get("item", [])
            if isinstance(items, dict): items = [items]
            return {
                "items": [{
                    "id":      str(r.get("hsmpSn", "")),
                    "name":    r.get("hsmpNm", ""),
                    "region":  f"{r.get('brtcNm','')} {r.get('signguNm','')}".strip(),
                    "type":    r.get("suplyTyNm", ""),
                    "units":   r.get("hshldCo", 0),
                    "area":    r.get("suplyPrvuseAr", 0),
                    "deposit": int(r.get("bassRentGtn", 0) or 0) // 10000,   # 원→만원
                    "rent":    int(r.get("bassMtRntchrg", 0) or 0) // 10000, # 원→만원
                    "moveIn":  r.get("competDe", ""),
                    "addr":    r.get("rnAdres", ""),
                    "org":     r.get("insttNm", ""),
                } for r in items],
                "total": len(items)
            }
        except Exception as e:
            return {"items": [], "total": 0, "debug": str(e)}

    # ────────────────────────────────────────────────────
    # 파서: LH 공고 (일반 + 사전청약 공용)
    # 응답 구조:
    #   일반:     [{dsSch:{...}}, {dsList:[{PAN_NM, CNP_CD_NM, PAN_NT_ST_DT,
    #                CLSG_DT, PAN_SS, DTL_URL, AIS_TP_CD_NM, UPP_AIS_TP_NM},...]}]
    #   사전청약: {"resHeader":{...}, "dsList":[{PAN_NM, CNP_CD_NM, PAN_NT_ST_DT,
    #                CLSG_DT, PAN_SS, DTL_URL, DTL_URL_MOB, AIS_TP_CD_NM},...]}
    # ────────────────────────────────────────────────────
    def _parse_lh_notices(self, data):
        try:
            rows = _extract_dsList(data)
            return {
                "items": [{
                    "id":        r.get("PAN_ID", ""),
                    "title":     r.get("PAN_NM", ""),
                    "type":      r.get("AIS_TP_CD_NM", r.get("UPP_AIS_TP_NM", "")),
                    "region":    r.get("CNP_CD_NM", ""),
                    "startDate": r.get("PAN_NT_ST_DT", r.get("PAN_ST_DT", "")),
                    "endDate":   r.get("CLSG_DT", r.get("PAN_ED_DT", "")),
                    "status":    r.get("PAN_SS", ""),
                    "url":       r.get("DTL_URL_MOB", r.get("DTL_URL", "")),
                } for r in rows],
                "total": len(rows)
            }
        except Exception as e:
            return {"items": [], "total": 0, "debug": str(e)}

    # ────────────────────────────────────────────────────
    # 파서: 아파트 전월세 실거래가
    # 응답: {"response":{"body":{"items":{"item":[{월세금액,...}]}}}}
    # ────────────────────────────────────────────────────
    def _parse_realprice(self, data):
        try:
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if isinstance(items, dict): items = [items]
            rents = [
                int(str(i.get("월세금액", 0)).replace(",", "") or 0)
                for i in items
                if int(str(i.get("월세금액", 0)).replace(",", "") or 0) > 0
            ]
            avg = int(sum(rents) / len(rents)) if rents else 0
            return {"avgMonthlyRent": avg, "count": len(rents), "items": items[:10]}
        except Exception as e:
            return {"avgMonthlyRent": 0, "count": 0, "debug": str(e)}

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[OK] Proxy server v2.0 → http://localhost:{PORT}")
    server.serve_forever()

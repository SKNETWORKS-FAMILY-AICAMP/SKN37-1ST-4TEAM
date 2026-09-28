import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def setup_stealth_driver():
    """
    크롤링 차단 모듈 우회 및 최적화된 스텔스 크롬 드라이버를 생성합니다.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # navigator.webdriver 속성을 감추어 자동화 탐지 차단
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

def scrape_hana_faq():
    target_url = "https://www.hanainsure.co.kr/w/customer/counselInquiry/faq"
    collected_data = []
    
    driver = setup_stealth_driver()
    wait = WebDriverWait(driver, 15)

    try:
        print("▶ [1/4] 하나손해보험 FAQ 페이지 접속 중...")
        driver.get(target_url)
        time.sleep(3)

        # -------------------------------------------------------------
        # 1. [최초 1회] 검색창에 "자동차" 입력 후 검색 버튼 클릭
        # -------------------------------------------------------------
        print("▶ [2/4] 최초 1회 '자동차' 키워드 검색 진행 중...")
        search_input = wait.until(EC.presence_of_element_located((By.ID, "txtSearchKey")))
        search_input.clear()
        search_input.send_keys("자동차")
        time.sleep(0.5)

        search_btn = driver.find_element(By.CSS_SELECTOR, "a.btnSearch")
        driver.execute_script("arguments[0].click();", search_btn)
        time.sleep(2.5)  # 검색 결과 AJAX 동적 반영 대기

        # -------------------------------------------------------------
        # 2. 항목(카테고리) 목록 파싱 및 비상(Fallback) 목록 설정
        # -------------------------------------------------------------
        print("▶ [3/4] 항목(카테고리) 목록 확인 중...")
        categories = []
        try:
            main_cate_btn = wait.until(EC.element_to_be_clickable((By.ID, "lnkMainCate")))
            driver.execute_script("arguments[0].click();", main_cate_btn)
            time.sleep(0.8)

            cate_elements = driver.find_elements(By.CSS_SELECTOR, "ul#mainCateList > li")
            for li in cate_elements:
                cat_code = li.get_attribute("data-category")
                cat_text = li.get_attribute("textContent").strip()
                if cat_code and cat_text and "전체" not in cat_text:
                    categories.append({"code": cat_code, "name": cat_text})
                    
            driver.execute_script("arguments[0].click();", main_cate_btn)
            time.sleep(0.5)
        except Exception:
            pass

        # 동적 추출 미작동 시 1번 이미지 규격 카테고리 자동 설정
        if not categories:
            categories = [
                {"code": "01", "name": "상품안내"},
                {"code": "07", "name": "홈페이지"},
                {"code": "02", "name": "보상서비스"},
                {"code": "03", "name": "대출"},
                {"code": "04", "name": "보험료계산/가입"}
            ]

        print(f" -> 최종 수집 대상 카테고리 ({len(categories)}개): {[c['name'] for c in categories]}")

        # -------------------------------------------------------------
        # 3. 항목별 순회 및 페이지 이동 데이터 수집
        # -------------------------------------------------------------
        print("▶ [4/4] 카테고리 및 페이지 순회 데이터 수집 시작...\n")
        
        for cate_info in categories:
            cat_code = cate_info["code"]
            cat_name = cate_info["name"]
            print(f"==================================================")
            print(f"[*] [카테고리] '{cat_name}' (코드: {cat_code}) 수집 진행")
            print(f"==================================================")

            # 드롭박스 열고 해당 카테고리 클릭
            try:
                main_cate_btn = wait.until(EC.element_to_be_clickable((By.ID, "lnkMainCate")))
                driver.execute_script("arguments[0].click();", main_cate_btn)
                time.sleep(0.5)

                cate_item = driver.find_element(By.CSS_SELECTOR, f"ul#mainCateList > li[data-category='{cat_code}'] > a")
                driver.execute_script("arguments[0].click();", cate_item)
                time.sleep(2)
            except Exception as e:
                print(f" [경고] 카테고리 '{cat_name}' 전환 중 알림: {e}")

            page_num = 1
            while True:
                print(f"  > [{cat_name}] {page_num}페이지 수집 진행 중...")
                
                faq_items = driver.find_elements(By.CSS_SELECTOR, "ul#targetFaqList > li")
                
                if not faq_items:
                    print("   - 등록된 질문/답변 데이터가 없습니다.")
                    break

                # 페이지 변경 여부 비교를 위한 이전 첫 질문 기록
                try:
                    first_q_before = faq_items[0].find_element(By.TAG_NAME, "a").get_attribute("textContent").strip()
                except Exception:
                    first_q_before = ""

                page_collected_count = 0

                # --- 질문/답변 파싱 ---
                for idx in range(len(faq_items)):
                    current_items = driver.find_elements(By.CSS_SELECTOR, "ul#targetFaqList > li")
                    if idx >= len(current_items):
                        break
                    
                    item = current_items[idx]
                    
                    # 1) 질문(Q) 파싱 및 아코디언 펼치기
                    try:
                        q_link = item.find_element(By.TAG_NAME, "a")
                        driver.execute_script("arguments[0].click();", q_link)
                        time.sleep(0.15)
                        raw_q = q_link.get_attribute("textContent").strip()
                    except Exception:
                        raw_q = ""

                    q_lines = [line.strip() for line in raw_q.split("\n") if line.strip()]
                    clean_q_lines = [line for line in q_lines if line != "Q"]
                    clean_q = " ".join(clean_q_lines)

                    if clean_q.startswith("Q.") or clean_q.startswith("Q ."):
                        clean_q = clean_q.split(".", 1)[-1].strip()
                    elif clean_q.startswith("Q"):
                        clean_q = clean_q[1:].strip()

                    # 2) 답변(A) 파싱
                    try:
                        ans_div = item.find_element(By.CSS_SELECTOR, "div")
                        raw_a = ans_div.get_attribute("textContent").strip()
                    except Exception:
                        raw_a = ""

                    a_lines = [line.strip() for line in raw_a.split("\n") if line.strip()]
                    clean_a_lines = [line for line in a_lines if line != "A"]
                    clean_a = " ".join(clean_a_lines)

                    if clean_a.startswith("A.") or clean_a.startswith("A ."):
                        clean_a = clean_a.split(".", 1)[-1].strip()
                    elif clean_a.startswith("A"):
                        clean_a = clean_a[1:].strip()

                    # 3) 질문 및 답변 내 쉼표(,) -> 공백 치환
                    clean_q = clean_q.replace(",", " ")
                    clean_a = clean_a.replace(",", " ")

                    if clean_q:
                        collected_data.append({
                            "항목": cat_name,
                            "질문": f"Q. {clean_q}",
                            "답변": f"A. {clean_a}"
                        })
                        page_collected_count += 1

                print(f"   - {page_collected_count}개 질문/답변 수집 완료")

                # -------------------------------------------------------------
                # 4. 스크린샷 HTML 반영 다음 페이지 이동 알고리즘
                # -------------------------------------------------------------
                moved_next = False
                target_page_str = str(page_num + 1)

                # [알고리즘 1단계] 숫자 페이지 버튼 클릭 시도 (ex: '2', '3'...)
                num_btns = driver.find_elements(By.XPATH, f"//a[text()='{target_page_str}' or normalize-space(text())='{target_page_str}']")
                for btn in num_btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        moved_next = True
                        break

                # [알고리즘 2단계] 숫자 버튼이 없는 경우, 올려주신 스크린샷 HTML 구조 (li.arrow.next > a) 클릭
                if not moved_next:
                    arrow_btns = driver.find_elements(By.CSS_SELECTOR, "li.arrow.next > a")
                    for arrow in arrow_btns:
                        try:
                            parent_li = arrow.find_element(By.XPATH, "./..")
                            li_class = parent_li.get_attribute("class") or ""
                            
                            # disabled / off 클래스가 포함되지 않은 클릭 가능한 화살표만 처리
                            if "disabled" not in li_class and "off" not in li_class:
                                driver.execute_script("arguments[0].click();", arrow)
                                moved_next = True
                                break
                        except Exception:
                            continue

                # 더 이상 이동 가능한 다음 페이지 버튼이 없을 때
                if not moved_next:
                    print(f"   -> [{cat_name}] 카테고리의 마지막 페이지입니다.")
                    break

                time.sleep(2.0)  # AJAX 데이터 로딩 안정적 대기

                # [알고리즘 3단계] 데이터 변동 검증 (페이지가 넘어가지 않는 현상 방지)
                try:
                    new_items = driver.find_elements(By.CSS_SELECTOR, "ul#targetFaqList > li")
                    if new_items:
                        first_q_after = new_items[0].find_element(By.TAG_NAME, "a").get_attribute("textContent").strip()
                        if first_q_before and first_q_before == first_q_after:
                            print(f"   -> [{cat_name}] 다음 페이지 데이터가 동일하므로 카테고리 수집을 종료합니다.")
                            break
                except Exception:
                    pass

                page_num += 1

        # -------------------------------------------------------------
        # 5. 수집 결과 CSV 저장 (utf-8-sig 인코딩)
        # -------------------------------------------------------------
        print("\n==================================================")
        print("▶ 데이터 수집 완료! CSV 파일 작성을 시작합니다...")
        df = pd.DataFrame(collected_data, columns=["항목", "질문", "답변"])
        
        output_filename = "hana_insurance_faq.csv"
        df.to_csv(output_filename, index=False, encoding="utf-8-sig")
        print(f"★ [성공] 총 {len(df)}건의 FAQ 데이터가 '{output_filename}' 파일로 저장되었습니다.")
        print("==================================================")

    except Exception as e:
        print(f"\n[오류 발생]: {e}")

    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_hana_faq()
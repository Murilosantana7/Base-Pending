import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import shutil
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

DOWNLOAD_DIR = "/tmp"

# ==============================
# Função de renomear arquivo
# ==============================
def rename_downloaded_file(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PEND-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
        shutil.move(download_path, new_file_path)
        print(f"Arquivo salvo como: {new_file_path}")
        return new_file_path
    except Exception as e:
        print(f"Erro ao renomear o arquivo: {e}")
        return None


# ==============================
# Função de atualização Google Sheets
# ==============================
def update_packing_google_sheets(csv_file_path):
    try:
        if not os.path.exists(csv_file_path):
            print(f"Arquivo {csv_file_path} não encontrado.")
            return
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("hxh.json", scope)
        client = gspread.authorize(creds)
        sheet1 = client.open_by_url(
            "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183"
        )
        worksheet1 = sheet1.worksheet("Base Pending")
        df = pd.read_csv(csv_file_path).fillna("")
        worksheet1.clear()
        worksheet1.update([df.columns.values.tolist()] + df.values.tolist())
        print(f"Arquivo enviado com sucesso para a aba 'Base Pending'.")
    except Exception as e:
        print(f"Erro durante o processo: {e}")


# ==============================
# Fluxo principal Playwright
# ==============================
async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        # Ajuste de viewport para garantir que elementos caibam na tela
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        try:
            # LOGIN
            print("🔐 Fazendo login no SPX...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops113074')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            
            await page.wait_for_load_state("networkidle", timeout=40000)

            # ================== TRATAMENTO DE POP-UP ==================
            print("⏳ Aguardando renderização do pop-up (10s)...")
            await page.wait_for_timeout(10000) 

            popup_closed = False

            # --- OPÇÃO 1: TECLA ESC ---
            print("1️⃣ Tentativa 1: Pressionando ESC (Método Rápido)...")
            try:
                viewport = page.viewport_size
                if viewport:
                    await page.mouse.click(viewport['width'] / 2, viewport['height'] / 2)
                
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
            except Exception as e:
                print(f"Erro no ESC: {e}")

            await page.wait_for_timeout(1000)

            # --- OPÇÃO 2: BOTÕES ---
            print("2️⃣ Tentativa 2: Procurando botões de fechar...")
            possible_buttons = [
                ".ssc-dialog-header .ssc-dialog-close-icon-wrapper",
                ".ssc-dialog-close-icon-wrapper",
                "svg.ssc-dialog-close",             
                ".ant-modal-close",               
                ".ant-modal-close-x",
                "[aria-label='Close']"
            ]

            for selector in possible_buttons:
                if await page.locator(selector).count() > 0:
                    print(f"⚠️ Botão encontrado: {selector}")
                    try:
                        await page.locator(selector).first.evaluate("element => element.click()")
                        print("✅ Clique JS realizado no botão.")
                        popup_closed = True
                        break
                    except:
                        try:
                            await page.locator(selector).first.click(force=True)
                            print("✅ Clique forçado realizado.")
                            popup_closed = True
                            break
                        except Exception as e:
                            print(f"Falha ao clicar em {selector}: {e}")
            
            # --- OPÇÃO 3: MÁSCARA/FUNDO ---
            if not popup_closed:
                print("3️⃣ Tentativa 3: Clicando no fundo escuro...")
                masks = [".ant-modal-mask", ".ssc-dialog-mask", ".ssc-modal-mask"]
                for mask in masks:
                    if await page.locator(mask).count() > 0:
                        try:
                            await page.locator(mask).first.click(position={"x": 10, "y": 10}, force=True)
                            print("✅ Clicado na máscara.")
                            break
                        except:
                            pass
            
            await page.wait_for_timeout(2000)
            # ==========================================================

            # ================== DOWNLOAD: PENDING ==================
            print("\nIniciando Download: Base Pending")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(12000)

            # Clicando no botão de exportação inicial
            print("📤 Clicando em exportar...")
            # Tenta clicar no primeiro botão de exportar que aparecer
            await page.get_by_role("button", name="Exportar").nth(0).click()
            await page.wait_for_timeout(12000)

            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(10000)
            
            # === SELEÇÃO DA ABA ===
            print("👆 Selecionando aba de exportação...")
            try:
                # Tenta clicar na aba, mas não falha se não conseguir (pode já estar nela)
                await page.get_by_text("Exportar tarefa").or_(page.get_by_text("Export Task")).click(force=True, timeout=5000)
                print("✅ Aba selecionada/focada.")
            except Exception:
                print("⚠️ Aviso: Seguindo para o download direto (aba pode já estar ativa).")

            print("⬇️ Aguardando renderização da lista...")
            await page.wait_for_timeout(5000) 

            # === DIAGNÓSTICO DE TELA (IMPORTANTE) ===
            # Isso vai salvar uma foto da tela caso o botão não seja encontrado depois
            debug_screenshot = os.path.join(DOWNLOAD_DIR, "debug_erro_tela.png")
            await page.screenshot(path=debug_screenshot, full_page=True)
            print(f"📸 Print de diagnóstico salvo preventivamente em: {debug_screenshot}")
            # ========================================

            async with page.expect_download(timeout=60000) as download_info:
                print("🔎 Procurando botão 'Baixar' ou 'Download'...")
                
                # ESTRATÉGIA: Procura por texto, não por role, pois é mais garantido
                # Procura 'Baixar' OU 'Download'
                btn_locator = page.locator("text=Baixar").or_(page.locator("text=Download")).first
                
                # Verifica se encontrou algo antes de clicar
                if await btn_locator.count() > 0:
                    print("✅ Botão encontrado! Clicando...")
                    await btn_locator.click(force=True)
                else:
                    # Tenta uma última vez pelo role button antigo
                    print("⚠️ Texto não achado. Tentando seletor antigo de botão...")
                    await page.get_by_role("button", name="Baixar").nth(0).click(force=True)

            download = await download_info.value
            download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(download_path)

            new_file_path = rename_downloaded_file(DOWNLOAD_DIR, download_path)
            if new_file_path:
                update_packing_google_sheets(new_file_path)

            print("\n✅ Processo Base Pending concluído com sucesso.")

        except Exception as e:
            print(f"❌ Erro fatal durante o processo: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

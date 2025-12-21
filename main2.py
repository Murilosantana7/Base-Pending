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
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # LOGIN
            print("🔐 Fazendo login no SPX...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=10000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops113074')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            await page.wait_for_load_state("networkidle", timeout=20000)

            # ================== TRATAMENTO DE POP-UP (ATUALIZADO) ==================
            print("⏳ Aguardando renderização do pop-up...")
            await page.wait_for_timeout(8000)

            print("🧹 Verificando existência de pop-ups...")
            
            # Lista de seletores incluindo o wrapper que descobrimos no print
            possible_close_buttons = [
                ".ssc-dialog-close-icon-wrapper", # O seletor correto da sua imagem
                ".ssc-dialog-close",            
                ".ant-modal-close",             
                ".ant-modal-close-x",           
                "button[aria-label='Close']",   
                ".ssc-modal-close"              
            ]

            popup_closed = False
            
            # 1. Tenta clicar no botão X
            for selector in possible_close_buttons:
                if await page.locator(selector).is_visible():
                    print(f"⚠️ Pop-up detectado! Fechando com: {selector}")
                    try:
                        await page.locator(selector).click()
                        popup_closed = True
                        await page.wait_for_timeout(1000)
                        break
                    except Exception as e:
                        print(f"Erro ao tentar clicar em {selector}: {e}")

            # 2. Se não fechou, garante o foco e usa ESC
            if not popup_closed:
                print("➡️ Botão não encontrado. Tentando ESC forçado...")
                try:
                    await page.mouse.click(10, 10) # Garante foco na janela
                    await page.keyboard.press("Escape")
                except Exception as e:
                    print(f"Erro ao pressionar ESC: {e}")
            
            await page.wait_for_timeout(2000)
            # =======================================================================

            # ================== DOWNLOAD: PENDING ==================
            print("\nIniciando Download: Base Pending")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(12000)

            # Clicando no botão de exportação (Exporta o filtro atual/padrão)
            print("📤 Clicando em exportar...")
            await page.get_by_role("button", name="Exportar").nth(0).click()
            await page.wait_for_timeout(12000)

            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            await page.wait_for_timeout(15000)
            await page.get_by_text("Exportar tarefa").click()

            print("⬇️ Aguardando download...")
            async with page.expect_download(timeout=60000) as download_info:
                await page.get_by_role("button", name="Baixar").nth(0).click()

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

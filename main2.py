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
        print(f"✅ Arquivo enviado com sucesso para a aba 'Base Pending'.")
    except Exception as e:
        print(f"❌ Erro durante o processo Sheets: {e}")

# ==============================
# Fluxo principal Playwright
# ==============================
async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with async_playwright() as p:
        # Use headless=True para rodar em servidores (GitHub Actions, etc)
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # LOGIN
            print("🔐 Fazendo login no SPX...")
            await page.goto("https://spx.shopee.com.br/")
            await page.wait_for_selector('xpath=//*[@placeholder="Ops ID"]', timeout=15000)
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops113074')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            
            await page.wait_for_load_state("networkidle", timeout=40000)

            # ================== TRATAMENTO DE POP-UP ==================
            print("⏳ Aguardando renderização do pop-up (10s)...")
            await page.wait_for_timeout(10000) 

            # Tentativa 1: ESC
            try:
                viewport = page.viewport_size
                if viewport:
                    await page.mouse.click(viewport['width'] / 2, viewport['height'] / 2)
                await page.keyboard.press("Escape")
            except: pass

            await page.wait_for_timeout(1000)

            # Tentativa 2: Botões de fechar (JS Click para ser mais forte)
            possible_buttons = [
                ".ssc-dialog-header .ssc-dialog-close-icon-wrapper",
                ".ssc-dialog-close-icon-wrapper",
                "svg.ssc-dialog-close",               
                ".ant-modal-close"
            ]
            for selector in possible_buttons:
                if await page.locator(selector).count() > 0:
                    try:
                        await page.locator(selector).first.evaluate("el => el.click()")
                        break
                    except: pass
            
            await page.wait_for_timeout(2000)

            # ================== DOWNLOAD: PENDING ==================
            print("\n🚚 Iniciando Download: Base Pending")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip")
            await page.wait_for_timeout(12000)

            print("📤 Clicando em exportar na página de viagens...")
            await page.get_by_role("button", name="Exportar").first.click()
            await page.wait_for_timeout(15000) # Tempo para o sistema processar a solicitação

            print("📂 Indo para o centro de tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter")
            
            # --- CORREÇÃO CRÍTICA AQUI ---
            await page.wait_for_timeout(15000) # Espera estendida para carregar a aba
            
            print("🖱️ Tentando selecionar a aba 'Exportar tarefa'...")
            # Usamos evaluate para garantir que o clique ocorra mesmo se houver sobreposição
            aba_exportar = page.locator('text="Exportar tarefa"')
            if await aba_exportar.count() > 0:
                await aba_exportar.first.evaluate("el => el.click()")
                print("✅ Aba selecionada via JS.")
            else:
                print("⚠️ Texto 'Exportar tarefa' não encontrado, tentando clique por posição...")
                await page.get_by_text("Exportar tarefa").click()

            await page.wait_for_timeout(8000)

            print("⬇️ Localizando botão de baixar...")
            async with page.expect_download(timeout=90000) as download_info:
                # Usando get_by_role para maior precisão como no seu script funcional
                await page.get_by_role("button", name="Baixar").first.click()

            download = await download_info.value
            download_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            await download.save_as(download_path)
            print(f"✅ Download concluído: {download_path}")

            new_file_path = rename_downloaded_file(DOWNLOAD_DIR, download_path)
            if new_file_path:
                update_packing_google_sheets(new_file_path)

            print("\n🎉 Processo Base Pending concluído com sucesso!")

        except Exception as e:
            print(f"❌ Erro fatal: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

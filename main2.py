import asyncio
import os
import shutil
import traceback
from datetime import datetime
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.async_api import async_playwright

# ================= CONFIGURAÇÕES =================
DOWNLOAD_DIR = "/tmp" 
HEADLESS_MODE = True # Voltei para True pois vi que você roda no runner do GitHub
CREDENTIALS_FILE = "hxh.json"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1LZ8WUrgN36Hk39f7qDrsRwvvIy1tRXLVbl3-wSQn-Pc/edit#gid=734921183"

# ================= FUNÇÕES AUXILIARES =================
def rename_downloaded_file(download_dir, download_path):
    try:
        current_hour = datetime.now().strftime("%H")
        new_file_name = f"PEND-{current_hour}.csv"
        new_file_path = os.path.join(download_dir, new_file_name)
        
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
            
        shutil.move(download_path, new_file_path)
        print(f"✅ Arquivo renomeado para: {new_file_path}")
        return new_file_path
    except Exception as e:
        print(f"❌ Erro ao renomear arquivo: {e}")
        return None

def update_packing_google_sheets(csv_file_path):
    if not csv_file_path or not os.path.exists(csv_file_path):
        print(f"⚠️ Arquivo CSV não encontrado: {csv_file_path}")
        return

    try:
        print("📊 Iniciando upload para o Google Sheets...")
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open_by_url(SHEET_URL)
        worksheet = sheet.worksheet("Base Pending")
        
        try:
            df = pd.read_csv(csv_file_path).fillna("")
        except pd.errors.EmptyDataError:
            print("⚠️ O arquivo CSV baixado está vazio. Pulando upload.")
            return

        worksheet.clear()
        if not df.empty:
            worksheet.update([df.columns.values.tolist()] + df.values.tolist())
            print(f"✅ Sheets atualizado com sucesso! ({len(df)} linhas)")
        else:
            print("⚠️ DataFrame vazio, planilha limpa.")
            
    except Exception as e:
        print(f"❌ Erro na integração com Sheets: {e}")

# ================= FLUXO PRINCIPAL =================
async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    async with async_playwright() as p:
        # Adicionei argumentos para evitar detecção de bot e melhorar estabilidade no Linux
        browser = await p.chromium.launch(
            headless=HEADLESS_MODE, 
            args=["--no-sandbox", "--disable-dev-shm-usage", "--start-maximized"]
        )
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        try:
            # --- LOGIN (Revertido para o Original) ---
            print("🔐 Acessando SPX...")
            await page.goto("https://spx.shopee.com.br/", wait_until="networkidle")
            
            # Usando seus XPaths originais que sabemos que funcionam
            await page.locator('xpath=//*[@placeholder="Ops ID"]').fill('Ops113074')
            await page.locator('xpath=//*[@placeholder="Senha"]').fill('@Shopee123')
            
            print("🔑 Clicando no botão de login...")
            # XPath original do botão
            await page.locator('xpath=/html/body/div[1]/div/div[2]/div/div/div[1]/div[3]/form/div/div/button').click()
            
            # --- TRATAMENTO DE POP-UP ---
            print("⏳ Verificando pop-ups...")
            try:
                # Espera curta para pop-up
                close_btn = page.locator(".ssc-dialog-close-icon-wrapper, .ant-modal-close, svg.ssc-dialog-close").first
                await close_btn.wait_for(state="visible", timeout=8000)
                await close_btn.click()
                print("✅ Pop-up fechado.")
            except:
                print("ℹ️ Nenhum pop-up detectado. Seguindo...")

            # --- NAVEGAÇÃO ---
            print("\n🚚 Acessando página de Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000) # Pequeno respiro para SPA carregar

            print("📤 Solicitando exportação...")
            # Tenta clicar no Exportar
            try:
                await page.get_by_role("button", name="Exportar").first.click()
            except:
                # Fallback se o botão mudar
                await page.locator('button:has-text("Exportar")').click()
            
            await page.wait_for_timeout(3000) 

            print("📂 Indo para Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter", wait_until="networkidle")
            
            # Seleção da aba
            print("Checking abas...")
            try:
                await page.locator('text="Exportar tarefa"').click(timeout=10000)
            except:
                print("⚠️ Aba não clicável ou já ativa.")

            print("⬇️ Buscando botão 'Baixar'...")
            download_btn = page.get_by_role("button", name="Baixar").first
            
            # Espera botão ficar visível
            await download_btn.wait_for(state="visible", timeout=60000)

            # --- DOWNLOAD COM CLIQUE FORÇADO (Correção da Imagem 1) ---
            print("🖱️ Tentando baixar...")
            async with page.expect_download(timeout=60000) as download_info:
                # Tenta 3 estratégias de clique em sequência
                try:
                    # 1. Clique forçado do Playwright
                    await download_btn.click(force=True, timeout=5000)
                except:
                    print("⚠️ Click padrão falhou, tentando JS...")
                    try:
                        # 2. Clique via JavaScript (infalível para sobreposições)
                        await download_btn.evaluate("el => el.click()")
                    except:
                        # 3. Disparar evento de click nativo
                        await download_btn.dispatch_event("click")

            download = await download_info.value
            temp_path = await download.path()
            final_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            shutil.move(temp_path, final_path)
            
            print(f"✅ Download salvo: {final_path}")

            # Processamento
            renamed_path = rename_downloaded_file(DOWNLOAD_DIR, final_path)
            if renamed_path:
                update_packing_google_sheets(renamed_path)

            print("\n🎉 Processo finalizado com sucesso!")

        except Exception as e:
            print(f"\n❌ ERRO CRÍTICO:")
            traceback.print_exc()
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

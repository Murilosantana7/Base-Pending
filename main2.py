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
DOWNLOAD_DIR = "/tmp" # Ou um caminho absoluto no Windows se for rodar local
HEADLESS_MODE = False # Mude para True quando rodar no servidor/GitHub Actions
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
        
        # Leitura robusta do CSV (trata arquivos vazios ou erros de encoding)
        try:
            df = pd.read_csv(csv_file_path).fillna("")
        except pd.errors.EmptyDataError:
            print("⚠️ O arquivo CSV baixado está vazio. Pulando upload.")
            return

        # Limpa e atualiza em uma única transação para evitar "piscar" a planilha
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
        browser = await p.chromium.launch(headless=HEADLESS_MODE, args=["--start-maximized"])
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        try:
            # --- LOGIN OTIMIZADO ---
            print("🔐 Acessando SPX...")
            await page.goto("https://spx.shopee.com.br/", wait_until="networkidle")
            
            # Seletores mais inteligentes (sem XPath complexo)
            await page.get_by_placeholder("Ops ID").fill('Ops113074')
            await page.get_by_placeholder("Senha").fill('@Shopee123')
            
            # Clica no botão de login e espera a navegação completar
            await page.get_by_role("button", name="Login").click() # Ajuste "name" se o texto do botão for diferente
            # Se o botão não tiver texto claro, use a classe: page.locator(".login-btn-class")
            
            print("⏳ Verificando pop-ups...")
            # --- TRATAMENTO DE POP-UP RÁPIDO ---
            # Espera no máximo 5s pelo pop-up. Se não aparecer, segue.
            try:
                # Seletor genérico para botão de fechar modal
                close_btn = page.locator(".ssc-dialog-close-icon-wrapper, .ant-modal-close, svg.ssc-dialog-close").first
                await close_btn.wait_for(state="visible", timeout=5000)
                await close_btn.click()
                print("✅ Pop-up fechado.")
            except:
                print("ℹ️ Nenhum pop-up detectado (ou fechou sozinho). Seguindo...")

            # --- DOWNLOAD FLOW ---
            print("\n🚚 Acessando página de Viagens...")
            await page.goto("https://spx.shopee.com.br/#/hubLinehaulTrips/trip", wait_until="domcontentloaded")
            
            # Espera botão Exportar estar visível e clicável
            print("📤 Solicitando exportação...")
            export_btn = page.get_by_role("button", name="Exportar").first
            await export_btn.wait_for(state="visible")
            await export_btn.click()
            
            # Pequena espera técnica para o backend registrar a solicitação (necessário em SPAs)
            await page.wait_for_timeout(2000) 

            print("📂 Indo para Centro de Tarefas...")
            await page.goto("https://spx.shopee.com.br/#/taskCenter/exportTaskCenter", wait_until="domcontentloaded")
            
            # Seleciona aba com espera inteligente
            print("Checking abas...")
            tab_locator = page.locator('text="Exportar tarefa"')
            await tab_locator.wait_for(state="visible", timeout=10000)
            await tab_locator.click() # Geralmente click simples funciona aqui se esperou visible

            print("⬇️ Buscando botão 'Baixar'...")
            # Espera pelo botão de Baixar aparecer na lista (pode demorar se o relatório for grande)
            download_btn = page.get_by_role("button", name="Baixar").first
            
            try:
                # Espera até 60s para o botão aparecer (o processamento do relatório pode demorar)
                await download_btn.wait_for(state="visible", timeout=60000)
            except:
                print("⚠️ Botão baixar não apareceu em 60s. Tentando recarregar a página...")
                await page.reload()
                await download_btn.wait_for(state="visible", timeout=30000)

            # --- O DOWNLOAD SEGURO ---
            async with page.expect_download(timeout=60000) as download_info:
                # AQUI ESTÁ A CORREÇÃO PRINCIPAL: Force=True e JS Fallback
                try:
                    await download_btn.click(force=True)
                except:
                    print("⚠️ Click padrão falhou, forçando via JS...")
                    await download_btn.evaluate("el => el.click()")

            download = await download_info.value
            temp_path = await download.path() # Caminho temporário seguro
            final_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
            shutil.move(temp_path, final_path)
            
            print(f"✅ Download original salvo: {final_path}")

            # Processamento final
            renamed_path = rename_downloaded_file(DOWNLOAD_DIR, final_path)
            if renamed_path:
                update_packing_google_sheets(renamed_path)

            print("\n🎉 Processo finalizado com sucesso!")

        except Exception as e:
            print(f"\n❌ ERRO CRÍTICO NO SCRIPT:")
            traceback.print_exc()
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

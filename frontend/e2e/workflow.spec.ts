import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {pages,fmt} from '../lib';
test('real workbook: financial controls, all pages, filters, exports, removal',async({page})=>{
const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('/');await expect(page.getByRole('heading',{name:'Pharma Sales Intelligence'})).toBeVisible();
await expect(page.locator('canvas')).toHaveCount(0);
await page.screenshot({path:'../reports/empty-desktop.png',fullPage:true});
const source=process.env.PHARMA_TEST_WORKBOOK||'C:/Users/keell/Downloads/pharma_sales_45000_with_material_master.xlsx';
await page.locator('input[type=file]').setInputFiles(source);
await expect(page.getByTestId('kpi-net')).toBeVisible({timeout:240000});
const report=JSON.parse(readFileSync('../reports/workbook-review.json','utf8'));
for(const k of ['net','gross','discount','quantity','invoices','discount_pct'])await expect(page.getByTestId('kpi-'+k)).toHaveText(fmt(report.api_measure_controls[k],k));
await page.screenshot({path:'../reports/overview-desktop.png',fullPage:true});
const before=await page.getByTestId('kpi-net').textContent();
await page.locator('.filter').filter({hasText:/^Therapy/}).locator('summary').click();
await page.locator('.filter-options').getByLabel('CVM',{exact:true}).check();
await expect(page.getByTestId('kpi-net')).not.toHaveText(before!);
await page.getByRole('button',{name:'Reset filters',exact:true}).click();
await expect(page.getByTestId('kpi-net')).toHaveText(before!);
await page.locator('.filter').filter({hasText:/^Therapy/}).locator('summary').click();
for(const [key] of pages){await page.locator('nav button').nth(pages.findIndex(p=>p[0]===key)).click();if(key==='explorer')await expect(page.locator('tbody tr').first()).toBeVisible();else await expect(page.getByTestId('kpi-net')).toBeVisible();await expect(page.locator('main [role=alert]')).toHaveCount(0);}
await page.locator('nav button').first().click();await expect(page.getByTestId('kpi-net')).toBeVisible();
await page.setViewportSize({width:390,height:844});await page.screenshot({path:'../reports/overview-mobile.png',fullPage:true});
expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
await page.setViewportSize({width:1440,height:1000});
for(const format of ['PDF','PowerPoint']){await page.getByRole('button',{name:'Export',exact:true}).click();const downloadPromise=page.waitForEvent('download',{timeout:180000});await page.getByRole('button',{name:'Download '+format,exact:true}).click();const file=await downloadPromise;await file.saveAs('../reports/verified-export.'+(format==='PDF'?'pdf':'pptx'));}
await page.getByRole('button',{name:'Clear all data',exact:true}).click();
await expect(page.getByRole('heading',{name:'Pharma Sales Intelligence'})).toBeVisible();await expect(page.locator('canvas')).toHaveCount(0);await expect(page.getByTestId('kpi-net')).toHaveCount(0);
expect(errors).toEqual([]);
});

test('combine two yearly files, compare, remove one, remove the final file',async({page})=>{
await page.goto('/');await page.locator('input[type=file]').setInputFiles(['../tests/fixtures/sales-2026.xlsx','../tests/fixtures/sales-2027.xlsx']);
await expect(page.getByTestId('kpi-net')).toHaveText('₹320');
await page.locator('nav button').nth(1).click();await expect(page.getByRole('heading',{name:'Compare fiscal years'})).toBeVisible();
await expect(page.getByText('2 matched active dates.',{exact:true})).toBeVisible();
for(const format of ['PDF','PowerPoint']){
  await page.getByRole('button',{name:'Export',exact:true}).click();
  const result=page.waitForEvent('download',{timeout:120000});
  await page.getByRole('button',{name:'Download '+format,exact:true}).click();
  expect(await (await result).failure()).toBeNull();
}
await page.locator('.dataset-label').click();await page.getByRole('button',{name:'Remove sales-2026.xlsx',exact:true}).click();
await expect(page.getByRole('button',{name:'Remove sales-2026.xlsx',exact:true})).toHaveCount(0);
await page.getByRole('button',{name:'Close dialog',exact:true}).click();await expect(page.getByTestId('kpi-net')).toHaveText('₹160');
await expect(page.getByRole('heading',{name:'Compare fiscal years'})).toHaveCount(0);
await page.locator('.dataset-label').click();await page.getByRole('button',{name:'Remove sales-2027.xlsx',exact:true}).click();
await expect(page.getByRole('heading',{name:'Pharma Sales Intelligence'})).toBeVisible();await expect(page.locator('canvas')).toHaveCount(0);
});

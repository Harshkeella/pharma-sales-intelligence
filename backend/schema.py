"""Explicit source aliases; IDs stay strings and invoice dates own the calendar."""
import re

def normalized(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).casefold()

FIELDS = {
 'date':['Invoice Date'], 'invoice':['Invoice Number'], 'customer':['Payer'], 'customer_name':['Payer Name'],
 'material':['Material'], 'product':['Mat Product Name'], 'description':['Material Description'],
 'quantity':['Quantity'], 'gross':['Sale Value'], 'net':['Net Amount'], 'discount_source':['Discount Value'],
 'division':['Sales Division Descr'], 'division_text':['Division Text'], 'plant':['Plant'], 'plant_name':['Plant Description'],
 'office':['SALES OFFICE DESCRIP','Sales Office Description'], 'group':['SALES GRP DESCRIPTIO','Sales Group Description'],
 'district':['SALES DISTRICT DESCR','Sales District Description'], 'city':['City'], 'ship_city':['Ship To Party City'],
 'customer_group':['Customer Group'], 'brand':['Mat Brand'], 'therapy':['Mat Therapy'], 'therapy1':['Mat Therapy 1'],
 'product_group':['Mat Product Group'], 'classification':['Mat Classification'], 'mother_brand':['Mat Mother Brand'],
 'portfolio':['Mat Division 1'], 'material_group':['Mat Group'], 'manufacturing':['Mat MFG'], 'storage':['Mat Temperature'],
 'transporter':['Transporter Name'], 'payment':['Payment term'], 'batch':['BATCH'], 'delivery_document':['Delivery Document'],
 'mrp':['MRP'], 'rate_before':['Rate Before Discount'], 'rate_after':['Rate After Discount'], 'discount_rate':['Discount Rate'],
 'cgst':['CGST Amount'], 'sgst':['SGST Amount'], 'igst':['IGST Amount','IGST Amount(INR)'], 'utgst':['UTGST Amount'],
 'cgst_rate':['CGST Rate'], 'sgst_rate':['SGST RATE'], 'igst_rate':['IGST RATE'], 'utgst_rate':['UTGST RATE'],
 'po_date':['P.O date'], 'order_date':['Sales order date'], 'delivery_date':['Delivery Date'], 'lr_date':['LR Date'],
 'mfg_date':['Mfg. Date'], 'expiry_date':['Expiry Date'], 'source_year':['Year'], 'source_month':['Month'],
 'item_category':['Item Catageroy','Item Category'], 'gross_tax':['Gross Amt(INR)'],
}
ALIASES = {normalized(a): k for k, names in FIELDS.items() for a in names}
REQUIRED = ['date','invoice','customer','material','quantity','gross','net']
RECOMMENDED = ['customer_name','brand','therapy','division','plant','discount_source','cgst','sgst','igst','utgst']
MONEY = ['gross','net','discount_source','cgst','sgst','igst','utgst','gross_tax']
NUMBERS = MONEY + ['quantity','mrp','rate_before','rate_after','discount_rate','cgst_rate','sgst_rate','igst_rate','utgst_rate']
DATES = ['date','po_date','order_date','delivery_date','lr_date','mfg_date','expiry_date']
DIMENSIONS = ['fiscal_year','year','month','division','therapy','brand','plant','district','customer','customer_name','product','material','classification','manufacturing','storage','office','group','customer_group','transporter','payment','city','ship_city','portfolio','therapy1','material_group','mother_brand','plant_name']
LABELS = {k:v[0] for k,v in FIELDS.items()} | {'fiscal_year':'Fiscal year','year':'Calendar year','month':'Month','net':'Net sales','gross':'Gross sales','customer':'Customer ID','manufacturing':'Manufacturing model','storage':'Storage condition','plant_name':'Plant location'}

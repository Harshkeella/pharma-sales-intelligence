import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',timeout:360000,expect:{timeout:15000},workers:1,use:{baseURL:'http://127.0.0.1:3000',headless:true,viewport:{width:1440,height:1000}},reporter:'list'});

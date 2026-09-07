import {describe,it,expect} from 'vitest';
import {fmt} from './lib';
describe('Business formatting',()=>{it('uses Indian units and distinguishes missing values from zero',()=>{expect(fmt(1276845346)).toBe('₹127.68 Cr');expect(fmt(1280000)).toBe('₹12.80 L');expect(fmt(null)).toBe('Unavailable');expect(fmt(0)).toBe('₹0');expect(fmt(15.02,'discount_pct')).toBe('15.02%');expect(fmt(-150000)).toBe('₹-1.50 L')})});

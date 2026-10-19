import { describe, it, expect } from 'vitest';
import {
  ROLE_RANK,
  mapEntraRoles,
  roleMeetsRequired,
  routeMinRole,
} from './msalConfig';

describe('role hierarchy', () => {
  it('ranks owner and admin at the top, worker at the bottom', () => {
    expect(ROLE_RANK.owner).toBe(ROLE_RANK.admin);
    expect(ROLE_RANK.admin).toBeGreaterThan(ROLE_RANK.manager);
    expect(ROLE_RANK.manager).toBeGreaterThan(ROLE_RANK.worker);
  });

  it('maps Entra app roles (incl. legacy Preduit.User)', () => {
    expect(mapEntraRoles(['Preduit.Owner'])).toBe('owner');
    expect(mapEntraRoles(['Preduit.Manager'])).toBe('manager');
    expect(mapEntraRoles(['Preduit.Worker'])).toBe('worker');
    expect(mapEntraRoles(['Preduit.User'])).toBe('worker'); // legacy
    // highest of several wins
    expect(mapEntraRoles(['Preduit.Worker', 'Preduit.Admin'])).toBe('admin');
  });

  it('enforces minimum roles', () => {
    expect(roleMeetsRequired('owner', 'admin')).toBe(true);
    expect(roleMeetsRequired('manager', 'admin')).toBe(false);
    expect(roleMeetsRequired('worker', 'manager')).toBe(false);
    expect(roleMeetsRequired('manager', 'worker')).toBe(true);
  });

  it('gates routes by minimum role', () => {
    expect(routeMinRole('/dashboard')).toBe('worker');
    expect(routeMinRole('/settings')).toBe('worker');
    expect(routeMinRole('/recommendations')).toBe('manager');
    expect(routeMinRole('/catalogue')).toBe('manager');
    expect(routeMinRole('/scope')).toBe('manager');
    expect(routeMinRole('/allocation')).toBe('manager');
    expect(routeMinRole('/purchase-orders')).toBe('manager');
    expect(routeMinRole('/login')).toBeNull();
  });
});

import type { ReactNode } from 'react';
import type { Role } from './api';

export interface FeatureModule {
  routes: { path: string; element: ReactNode; roles: Role[] }[];
  navigation: { to: string; label: string; roles: Role[] }[];
}


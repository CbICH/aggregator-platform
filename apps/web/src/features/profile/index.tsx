import type { FeatureModule } from '../../shared/module';
import { ProfilePage } from './ProfilePage';
import { PrivacyPage } from './PrivacyPage';
import { FspPage } from './FspPage';

export const profile: FeatureModule = {
  routes: [{ path: '/candidate/profile', element: <ProfilePage />, roles: ['candidate'] }, { path: '/candidate/privacy', element: <PrivacyPage />, roles: ['candidate'] }, { path: '/candidate/fsp', element: <FspPage />, roles: ['candidate'] }],
  navigation: [{ to: '/candidate/profile', label: 'Мой профиль', roles: ['candidate'] }],
};

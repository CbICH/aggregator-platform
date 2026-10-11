import type { FeatureModule } from '../../shared/module';
import { CandidateDirectory, ContactPage, InvitationForm, InvitationListPage, InvitationPage } from './Invitations';

export const invitations: FeatureModule = {
  routes: [
    { path: '/candidate/invitations', element: <InvitationListPage />, roles: ['candidate'] },
    { path: '/candidate/invitations/:id', element: <InvitationPage />, roles: ['candidate'] },
    { path: '/employer/invitations', element: <InvitationListPage />, roles: ['employer'] },
    { path: '/employer/invitations/new', element: <InvitationForm />, roles: ['employer'] },
    { path: '/employer/invitations/:id', element: <InvitationPage />, roles: ['employer'] },
    { path: '/employer/candidates', element: <CandidateDirectory />, roles: ['employer'] },
    { path: '/employer/candidates/:id/contacts', element: <ContactPage />, roles: ['employer'] },
  ],
  navigation: [
    { to: '/candidate/invitations', label: 'Приглашения', roles: ['candidate'] },
    { to: '/employer/invitations', label: 'Приглашения', roles: ['employer'] },
    { to: '/employer/candidates', label: 'Кандидаты', roles: ['employer'] },
  ],
};

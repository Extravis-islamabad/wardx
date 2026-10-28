/** WardX roles, as the backend issues them on `/auth/me`. */
export enum Role {
  ADMIN = 'admin',
  APPROVER = 'approver',
  AUDITOR = 'auditor',
  USER = 'user',
}

export enum AuthSource {
  LOCAL = 'local',
  LDAP = 'ldap',
}

/** Window events the API client raises for the auth context to act on. */
export enum AuthEvent {
  LOGOUT = 'wardx:logout',
  MFA_ENROL = 'wardx:mfa-enrol',
}

export enum ApiErrorCode {
  MFA_ENROLLMENT_REQUIRED = 'mfa_enrollment_required',
}

export enum HttpStatus {
  UNAUTHORIZED = 401,
}

export enum NotifyType {
  SUCCESS = 'success',
  ERROR = 'error',
  INFO = 'info',
  WARNING = 'warning',
}

export enum ErrorStateVariant {
  /** Above content that still shows. */
  BANNER = 'banner',
  /** Where the content would have been. */
  BLOCK = 'block',
}

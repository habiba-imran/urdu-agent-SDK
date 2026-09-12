declare module 'node:crypto' {
  interface Digestible {
    update(data: string): Digestible;
    digest(encoding: 'hex'): string;
  }

  export function createHash(algorithm: 'sha256'): Digestible;
  export function createHmac(algorithm: 'sha256', key: string): Digestible;
  export function randomUUID(): string;
}

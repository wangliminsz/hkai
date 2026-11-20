import { Md5 } from 'ts-md5';

export function md5(value: string): string {
  return Md5.hashStr(value) as unknown as string;
}

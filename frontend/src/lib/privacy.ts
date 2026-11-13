export const CLOAKED_TRANSPORT_SUBJECT = 'Encrypted QuMail Message';

const CLOAK_HEADER_PREFIX = '[QuMail-Subject]:';

const TRACKING_PARAMS = new Set([
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'utm_term',
  'utm_content',
  'utm_id',
  'fbclid',
  'gclid',
  'dclid',
  'msclkid',
  'mc_cid',
  'mc_eid',
  'igshid',
]);

export function embedCloakedSubject(realSubject: string, body: string): string {
  const cleanSubject = (realSubject || '(No Subject)').trim();
  return `${CLOAK_HEADER_PREFIX} ${cleanSubject}\n\n${body}`;
}

export function resolveDisplaySubject(msg: {
  subject?: string;
  body?: string;
}): {
  displaySubject: string;
  isCloaked: boolean;
  cleanBody: string;
} {
  const rawSubject = msg.subject || '(No Subject)';
  const rawBody = msg.body || '';

  if (rawBody.startsWith(CLOAK_HEADER_PREFIX)) {
    const firstNewline = rawBody.indexOf('\n');
    const firstLine = firstNewline === -1 ? rawBody : rawBody.slice(0, firstNewline);
    const extracted = firstLine.slice(CLOAK_HEADER_PREFIX.length).trim();
    const rest = firstNewline === -1 ? '' : rawBody.slice(firstNewline + 1).replace(/^\n+/, '');
    if (extracted) {
      return {
        displaySubject: extracted,
        isCloaked: true,
        cleanBody: rest,
      };
    }
  }

  return {
    displaySubject: rawSubject,
    isCloaked: rawSubject === CLOAKED_TRANSPORT_SUBJECT,
    cleanBody: rawBody,
  };
}

export function sanitizeExternalUrl(rawUrl: string): {
  cleanUrl: string;
  strippedParams: string[];
} {
  try {
    const parsed = new URL(rawUrl);
    const strippedParams: string[] = [];
    for (const key of Array.from(parsed.searchParams.keys())) {
      if (TRACKING_PARAMS.has(key.toLowerCase()) || key.toLowerCase().startsWith('utm_')) {
        strippedParams.push(key);
        parsed.searchParams.delete(key);
      }
    }
    return {
      cleanUrl: parsed.toString(),
      strippedParams,
    };
  } catch {
    return {
      cleanUrl: rawUrl,
      strippedParams: [],
    };
  }
}

export function expiryStringToHours(exp: '24h' | '7d' | '30d'): 24 | 168 | 720 {
  if (exp === '24h') return 24;
  if (exp === '30d') return 720;
  return 168;
}


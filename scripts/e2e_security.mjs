/**
 * End-to-end security & authorization validation script for BrandPR.
 *
 * Verifies:
 * 1. Missing Authorization header returns 401 Unauthorized.
 * 2. Spoofed X-Actor-* headers without valid Bearer token return 401 Unauthorized.
 * 3. Tampered/invalid JWT token returns 401 Unauthorized.
 * 4. Authenticated creator role cannot approve content (403 reviewer_role_required).
 * 5. Authenticated creator role cannot resolve fact impacts (403 reviewer_role_required).
 * 6. Authenticated creator role cannot release a campaign (403 reviewer_role_required).
 * 7. Scoped user (Eve) cannot access another brand's resources (403 brand_access_denied).
 * 8. Reviewer attempting to release a blocked campaign gets 409 Conflict.
 */

const BASE_URL = process.env.BASE_URL || 'https://brandpr-frontend-1009482348804.asia-south1.run.app';

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
  console.log(`PASS: ${message}`);
}

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  let body = null;
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    body = await res.json();
  } else {
    body = await res.text();
  }
  return { status: res.status, body };
}

async function run() {
  console.log(`Testing BrandPR Security Suite against: ${BASE_URL}`);

  // Setup: create a test brand as creator
  const creatorLogin = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: 'creator@brandpr.internal', password: 'brandpr_creator_demo' }),
  });
  assert(creatorLogin.status === 200, 'Creator login returns 200 with JWT');
  const creatorToken = creatorLogin.body.access_token;
  assert(typeof creatorToken === 'string' && creatorToken.split('.').length === 3, 'Creator token is a valid 3-part JWT');

  const reviewerLogin = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: 'reviewer@brandpr.internal', password: 'brandpr_reviewer_demo' }),
  });
  assert(reviewerLogin.status === 200, 'Reviewer login returns 200 with JWT');
  const reviewerToken = reviewerLogin.body.access_token;

  const eveLogin = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: 'eve@external.internal', password: 'brandpr_eve_demo' }),
  });
  assert(eveLogin.status === 200, 'Eve login returns 200 with JWT');
  const eveToken = eveLogin.body.access_token;

  // 1. Unauthenticated request to protected operation
  const unauthDecision = await request('/api/content/00000000-0000-0000-0000-000000000000/decisions', {
    method: 'POST',
    body: JSON.stringify({ decision: 'approved', notes: 'Hacked' }),
  });
  assert(unauthDecision.status === 401, `Unauthenticated request returns 401 (got ${unauthDecision.status})`);

  // 2. Caller-asserted X-Actor-Role header spoofing without Bearer token
  const spoofedHeaderDecision = await request('/api/content/00000000-0000-0000-0000-000000000000/decisions', {
    method: 'POST',
    headers: {
      'X-Actor-Name': 'Alex Compliance',
      'X-Actor-Role': 'reviewer',
    },
    body: JSON.stringify({ decision: 'approved', notes: 'Forged header' }),
  });
  assert(spoofedHeaderDecision.status === 401, `Spoofed X-Actor-* header without Bearer token rejected with 401 (got ${spoofedHeaderDecision.status})`);

  // 3. Tampered JWT signature
  const tamperedToken = creatorToken.slice(0, -5) + 'xxxxx';
  const tamperedReq = await request('/api/auth/me', {
    headers: { Authorization: `Bearer ${tamperedToken}` },
  });
  assert(tamperedReq.status === 401, `Tampered JWT token rejected with 401 (got ${tamperedReq.status})`);

  // Create brand and campaign for resource-level testing
  const brandRes = await request('/api/brands', {
    method: 'POST',
    headers: { Authorization: `Bearer ${creatorToken}` },
    body: JSON.stringify({ name: `Security Test Brand ${Date.now()}` }),
  });
  assert(brandRes.status === 201, 'Brand created successfully with Creator token');
  const brandId = brandRes.body.id;

  // 4. Scoped access: Eve (restricted to other brand) attempting to access this brand
  const eveAccessDocs = await request(`/api/brands/${brandId}/documents`, {
    headers: { Authorization: `Bearer ${eveToken}` },
  });
  assert(eveAccessDocs.status === 403, `Unauthorized user Eve denied access to brand documents (got ${eveAccessDocs.status}, code: ${eveAccessDocs.body?.error?.code})`);

  const eveAccessFacts = await request(`/api/brands/${brandId}/facts`, {
    headers: { Authorization: `Bearer ${eveToken}` },
  });
  assert(eveAccessFacts.status === 403, `Unauthorized user Eve denied access to brand facts (got ${eveAccessFacts.status}, code: ${eveAccessFacts.body?.error?.code})`);

  const eveAccessCampaigns = await request(`/api/brands/${brandId}/campaigns`, {
    headers: { Authorization: `Bearer ${eveToken}` },
  });
  assert(eveAccessCampaigns.status === 403, `Unauthorized user Eve denied access to brand campaigns (got ${eveAccessCampaigns.status}, code: ${eveAccessCampaigns.body?.error?.code})`);

  // Create content item as creator
  const contentRes = await request(`/api/brands/${brandId}/content`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${creatorToken}` },
    body: JSON.stringify({
      title: 'Security Draft',
      content: 'Our product has 99.9% uptime according to audited internal tests.',
    }),
  });
  assert(contentRes.status === 201, 'Content item created as creator');
  const contentId = contentRes.body.id;

  // 5. Creator attempting to approve content -> MUST FAIL with 403 reviewer_role_required
  const creatorApprove = await request(`/api/content/${contentId}/decisions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${creatorToken}` },
    body: JSON.stringify({ decision: 'approved', notes: 'Creator approving own work' }),
  });
  assert(creatorApprove.status === 403, `Creator attempting to approve content rejected with 403 (got ${creatorApprove.status})`);
  assert(creatorApprove.body?.error?.code === 'reviewer_role_required', `Error code is reviewer_role_required (got ${creatorApprove.body?.error?.code})`);

  // 6. Creator attempting to resolve/dismiss fact-change impacts -> MUST FAIL with 403 reviewer_role_required
  const creatorDismiss = await request(`/api/fact-change-impacts/00000000-0000-0000-0000-000000000000/dismiss`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${creatorToken}` },
    body: JSON.stringify({ rationale: 'Creator attempting dismissal without permission' }),
  });
  assert(creatorDismiss.status === 403, `Creator attempting to dismiss fact impact rejected with 403 (got ${creatorDismiss.status})`);
  assert(creatorDismiss.body?.error?.code === 'reviewer_role_required', `Error code is reviewer_role_required (got ${creatorDismiss.body?.error?.code})`);

  // 7. Create a campaign and test release authorization
  const campaignRes = await request(`/api/brands/${brandId}/campaigns`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${creatorToken}` },
    body: JSON.stringify({
      title: 'Q4 Launch',
      description: 'Q4 Security Campaign',
    }),
  });
  assert(campaignRes.status === 201, 'Campaign created');
  const campaignId = campaignRes.body.id;

  // Add the unapproved content item to the campaign
  await request(`/api/campaigns/${campaignId}/assets`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${creatorToken}` },
    body: JSON.stringify({ asset_id: contentRes.body.asset_id }),
  });

  // Run audit on the campaign
  await request(`/api/campaigns/${campaignId}/audits`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${creatorToken}` },
  });

  // Creator attempting to release campaign -> MUST FAIL with 403 reviewer_role_required
  const creatorRelease = await request(`/api/campaigns/${campaignId}/release`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${creatorToken}` },
    body: JSON.stringify({ release_notes: 'Creator attempting release' }),
  });
  assert(creatorRelease.status === 403, `Creator attempting to release campaign rejected with 403 (got ${creatorRelease.status})`);
  assert(creatorRelease.body?.error?.code === 'reviewer_role_required', `Error code is reviewer_role_required (got ${creatorRelease.body?.error?.code})`);

  // 8. Reviewer attempting to release a blocked campaign -> MUST FAIL with code release_blocked
  const reviewerBlockedRelease = await request(`/api/campaigns/${campaignId}/release`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${reviewerToken}` },
    body: JSON.stringify({ release_notes: 'Reviewer attempting release on blocked campaign' }),
  });
  assert([409, 422].includes(reviewerBlockedRelease.status), `Reviewer cannot release blocked campaign (got ${reviewerBlockedRelease.status}, code: ${reviewerBlockedRelease.body?.error?.code})`);
  assert(reviewerBlockedRelease.body?.error?.code === 'release_blocked' || reviewerBlockedRelease.body?.error?.code === 'campaign_release_blocked', `Error code indicates release blocked (got ${reviewerBlockedRelease.body?.error?.code})`);

  console.log('\nALL 8 SECURITY & AUTHORIZATION TESTS PASSED SUCCESSFULLY!');
}

run().catch((err) => {
  console.error('Security test failed with unexpected error:', err);
  process.exit(1);
});

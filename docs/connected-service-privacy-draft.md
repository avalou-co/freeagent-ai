# Connected-service privacy notice — draft for owner approval

This draft supplements the website notice. It is not approved for publication or
an invitation to connect. Owner approval is required before live account linking.

Avalou operates FreeAgent AI. Contact hello@avalou.co for privacy questions,
deletion requests and support. The controlled experiment permits only approved
Auth0 users and read-only accounting requests.

Auth0 processes your application sign-in. FreeAgent processes your separate
company authorization. We store an Auth0 subject identifier, linked company URL,
environment, encrypted FreeAgent access and refresh tokens, and connection
versions/cutoff timestamps in Google Cloud Firestore. Encryption keys are held
separately in Google Secret Manager. Temporary login state and browser sessions
support callback security and expire; expiry prevents use even before storage
cleanup. Browser cookies are Secure and HttpOnly.

When you request a read in ChatGPT, FreeAgent AI retrieves the requested data
from your linked FreeAgent company and returns it to ChatGPT. Accounting data
may include personal and financial information about you and your contacts.
ChatGPT/OpenAI, Auth0, FreeAgent and Google process data under their own terms
and applicable service agreements. Only connect data you are permitted to share.

Disconnect removes the active encrypted credential record and retains a connection
version and cutoff marker so old authorizations cannot regain access. It does not
delete records held by FreeAgent or prior results in ChatGPT. Disconnect the
ChatGPT connection separately and use the provider's controls for its retained
data. Auth0 maintains its own user account and authorization records.

Owner decisions required before publication: confirm lawful bases, processor
agreements and international transfer safeguards; confirm platform log retention,
callback-code protection and temporary-state cleanup; specify retention/deletion
periods for inactive subject markers and support enquiries, and the process for
handling access/deletion requests. Optional database backups remain disabled.
The website notice explains contact rights and the right to complain to the ICO.

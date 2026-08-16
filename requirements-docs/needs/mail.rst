Mail DNS
========

.. req:: Mail server IP
   :id: REQ_MAIL_001
   :status: implemented
   :tags: mail, dns

   The mail server entry (``mail.chilicode.com``) shall define expected IP
   ``37.16.72.84`` for DNS validation of mail-hosted domains.

.. req:: MX record check
   :id: REQ_MAIL_002
   :status: implemented
   :tags: mail, dns

   For domains on the mail server (excluding ``mail.*`` webmail vhosts), the
   checker shall resolve MX records and record priority and host for each entry.

.. req:: SPF record check
   :id: REQ_MAIL_003
   :status: implemented
   :tags: mail, dns

   For mail-server domains, the checker shall look for a TXT record starting
   with ``v=spf1``.

.. req:: DMARC record check
   :id: REQ_MAIL_004
   :status: implemented
   :tags: mail, dns

   For mail-server domains, the checker shall look for a TXT record at
   ``_dmarc.<domain>`` starting with ``v=DMARC1``.

.. req:: Mail DNS in report
   :id: REQ_MAIL_005
   :status: implemented
   :tags: mail, report

   The HTML report shall show MX/SPF/DMARC summary in the Mail column for
   mail-server domains.

.. spec:: Mail DNS schema
   :id: SPEC_MAIL_001
   :links: REQ_MAIL_002, REQ_MAIL_003, REQ_MAIL_004
   :status: implemented
   :tags: mail

   ``mail_dns`` object on mail-server domains: ``mx``, ``spf``, ``dmarc``,
   ``issues``, ``ok``.

.. impl:: check_domains.py (mail DNS)
   :id: IMPL_MAIL_001
   :links: REQ_MAIL_002, REQ_MAIL_003, REQ_MAIL_004
   :status: implemented
   :tags: mail

   Uses ``dnspython`` for MX and TXT lookups.

.. impl:: dnspython dependency
   :id: IMPL_MAIL_002
   :links: IMPL_MAIL_001
   :status: implemented
   :tags: mail

   ``dnspython>=2.0`` listed in ``requirements.txt``.

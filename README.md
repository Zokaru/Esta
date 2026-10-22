# ESTA
Minimal Static Site Generator

## About

ESTA is a simple Python script with the bare minimum needed in order to develop and deploy static websites made in pure HTML/CSS/JS.

ESTA is minimal by design: lightweight, performant, and easy to setup (zero dependencies besides Python itself).

ESTA's use case is simple websites that don't rely too much on server-side code and/or aren't updated too frequently: personal websites, portfolios, and small businesses. As a rule of thumb, if your server-side code is limited to a simple contact form, and you don't need to upload a blog post every day, then ESTA is for you.

ESTA is ideal for Github Pages and similar services. I created it for my personal website, https://zokaru.github.io/.

### Features

- Templates with nesting and custom attributes.
- Simple localisation.
- Cache-friendly asset management.
- CSS and JS bundling.
- Routing.
- Basic syntax check for HTML and CSS.

## Requirements

- Python 3

## Installation

1. If you don't have it, install Python 3 (https://www.python.org/).
2. Create a config file using the included [config.ini.sample](/config.ini.sample) as reference.
3. Run `python esta.py build -c CONFIG_FILE`, with CONFIG_FILE being the location of your config file.

## Usage

### Templates

Store templates as HTML files in the templates directory you defined in the config file.

Use templates by using the `<esta-template>` HTML tag:

```html
<esta-template template="name"></esta-template>
```

with `name` being the filename (without extension) of the HTML template located in your 'templates' folder.

You can also pass values to a template by using attributes. For example, let's say we have a template called heading.html with the following contents:

```html
<div class="heading {{ theme }}">
    <h1>{{ t: '{{ text }}' }}</h1>
</div>
```

We can reference 'theme' and 'text' when we instance the template like this:

```html
<esta-template template="heading" theme="dark" text="contact.title"></esta-template>
```

And the final result will be:

```html
<div class="heading dark">
    <h1>Contact</h1>
</div>
```

Where did the text 'Contact' came from? By using the next feature: translations.

### Translations

Multi-language support is handled by using translation files located in the 'lang' folder. You should make one JSON file for each language you want to support, named using a BCP 47 language subtag (like en, es, fr, etc). Use a key-based notation for your translations, like in the following example:

```json
{
    "key": "value",
    "hello": "Hello",
    "foo": {
        "bar": "bar",
    }
}
```

In order to access keys in templates and pages, use `{{ t: 'key' }}`, with `key` being a key from your translation files. Make sure all language files include all of the keys in use.

Example:

```html
`<h1>{{ t: 'header.title' }}</h1>`
```

Note: Translations are extremely barebores at the moment, with no support for plural forms, variations by context, or nesting. If you need advanced localisation features, it is recommended to use an external library or framework like [i18next](https://www.i18next.com/).

### Assets

Link assets (images, video, fonts, etc) using `{{ asset: 'path' }}`, with `path` being the relative path to a resource located in your 'assets' folder.

Example: `<img src="{{ asset: 'img/sample.jpg' }}">`

### Links

Internal links to any HTML document in your website can be resolved automatically.

Add links to internal pages using `{{ page: 'path' }}`, with `path` being the path to an HTML document in your 'pages' folder.

For example, `<a href="{{ page: 'blog/christmas.html' }}"></a>` will resolve as `<a href="https://mywebsite.com/en/blog/christmas.html"></a>` (assuming the visitor is accessing the website in English).

Important: You must set a 'base_url' in your config file for this to work.

If you want to specify a language instead of automatically using the current one, add a 'lang' parameter:

`{{ page: 'path' lang: 'key' }}`

This is useful for implementing language selectors, for example.

## License

GNU GENERAL PUBLIC LICENSE Version 3: [LICENSE](/LICENSE).
